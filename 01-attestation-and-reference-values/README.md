# Tutorial 01: Attestation and Reference Values

Build a TEE oracle and verify its attestation end-to-end.

This section covers:
- Using the Dstack SDK and guest interface
- Using the simulator dstack socket
- Binding data to TDX quotes via `report_data`

## Running Example: a TEE Oracle

Throughout this tutorial we will have a running example of an oracle, meaning an application that fetches data from some authoritative source, and then signs or attests to it so that it can be important, for example into a blockchain smart contract.

```
┌─────────────────────────────────────────────────────────────────┐
│                         TEE Oracle                              │
│                                                                 │
│  1. Fetch price from api.coingecko.com                          │
│  2. Capture TLS certificate fingerprint                         │
│  3. Build statement: { price, tlsFingerprint, timestamp }       │
│  4. Get TDX quote with sha256(statement) as report_data         │
│  5. Return { statement, quote }                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

This is a TLS oracle, meaning The TLS fingerprint proves which server the TEE connected to. The quote proves the statement came from this exact code running in a TEE.

> **Production hardening:** For higher assurance TLS verification (OCSP stapling, CRL checking, Certificate Transparency), see the [hardened-https-agent](https://github.com/Gldywn/hardened-https-agent) library and [phala-cloud-oracle-template](https://github.com/Gldywn/phala-cloud-oracle-template).

## Run Locally

```bash
# Start the simulator
phala simulator start

# Run the oracle
docker compose run --rm -p 8080:8080 \
  -v ~/.phala-cloud/simulator/0.5.3/dstack.sock:/var/run/dstack.sock \
  app
```

## Endpoints

**GET /** — App info and available endpoints

**GET /price** — Attested BTC price
```json
{
  "statement": {
    "source": "api.coingecko.com",
    "price": 97234.00,
    "tlsFingerprint": "5A:3B:...:F2",
    "tlsIssuer": "Cloudflare, Inc.",
    "tlsValidTo": "Dec 31 2025",
    "timestamp": 1703347200000
  },
  "reportDataHash": "a1b2c3...",
  "quote": "BAACAQI..."
}
```

---

## Exercises

### Exercise 1: Explore the oracle code

Open `docker-compose.yaml` and find where `report_data` is bound to the statement hash.

### Exercise 2: Modify and rebuild

Change the oracle to fetch ETH price instead of BTC. Rebuild and run. Does the compose-hash change?

### Exercise 3: Audit a public app

Pick any app from [trust.phala.com](https://trust.phala.com) and audit it:

```bash
python3 verify.py c951a6fa03ebc23bc469916476a51977219bc2a2
```

Questions to consider:
- What Docker images does it run? Are they from a source you trust?
- What `allowed_envs` can be injected at runtime? Could any change security-critical behavior?
- Is there a `pre_launch_script`? What does it do?
- Can you find the source code for the images?

### Exercise 4: Runtime vs compose-hash

If you passed `API_URL` as a runtime environment variable instead of hardcoding it, would the compose-hash change? Why or why not?

---

## Deploy to Phala Cloud

```bash
phala deploy -n tee-oracle -c docker-compose.yaml
```

---

## Verification

The quote contains **measured values**. Verification means comparing them against **reference values** you trust.

### Reference Values: Where They Come From

| Measured Value | Reference Value | How It's Verified |
|----------------|-----------------|-------------------|
| Intel signature | Intel root CA | Intel (built into dcap-qvl) |
| MRTD, RTMR0-2 | Hash of OS image | [Reproducibly build meta-dstack](https://github.com/Dstack-TEE/meta-dstack) |
| compose-hash (RTMR3) | `sha256(app-compose.json)` | [Build locally with vmm-cli](#building-app-composejson-locally) |
| report_data | `sha256(statement)` | Computed from output |
| tlsFingerprint | Certificate fingerprint | Fetch from api.coingecko.com |

This is the core insight: **attestation is only as trustworthy as your reference values.**

Dstack is designed around **reproducible builds** at every layer:
- **Hardware** — Intel provides attestation infrastructure
- **OS layer** — meta-dstack is open source and reproducibly built (see [meta-dstack](https://github.com/Dstack-TEE/meta-dstack))
- **App layer** — You can build `app-compose.json` locally and compute the exact hash

### The 8090 Endpoint

Every dstack CVM runs a **guest-agent** service on port 8090. This is not your application code — it's part of the dstack OS that provides public metadata about the enclave:

- `/` — Dashboard showing app_id, instance_id, TCB info, running containers
- `/logs/<container>` — Container logs (if `public_logs: true` in app-compose)
- `/metrics` — Prometheus metrics (if `public_sysinfo: true`)

The visibility is controlled by your `app-compose.json`. The code is part of [dstack-guest-agent](https://github.com/Dstack-TEE/dstack/tree/master/guest-agent).

### Verify Any Public App

Use the included script to audit any app on [trust.phala.com](https://trust.phala.com):

```bash
python3 verify.py c951a6fa03ebc23bc469916476a51977219bc2a2
```

Output:
```
=== Verifying Public App: c951a6fa03ebc23bc469916476a51977219bc2a2 ===

Step 1: Fetching attestation from Phala Cloud API...
  ✓ Found 1 instance(s)
  KMS version: v0.5.3 (git:ca4af023e974427e4153)
  Image: dstack-0.5.4.1

Step 2: Fetching app_compose from app endpoint...
  ✓ App name: primus-attestor-node
  Manifest version: 2
  KMS enabled: True
  Allowed envs: ['PRIVATE_KEY', 'BASE_RPC_URL', ...]

Step 3: Verifying compose hash...
  Computed hash: c211d18cc851609f...

=== Audit Summary ===
Docker images in compose:
  image: redis:latest
  image: primuslabs/attestor-node:${IMAGE_TAG}
  ...
```

For hardware verification (optional), install `dcap-qvl-cli`:
```bash
CFLAGS="-g0" cargo install dcap-qvl-cli
```

---

### Building app-compose.json Locally

The compose-hash in RTMR3 is the SHA-256 of an `app-compose.json` manifest. This is **not opaque** — the structure is simple and you can build it yourself:

```python
import json

app_compose = {
    "manifest_version": 2,
    "name": "tee-oracle",
    "runner": "docker-compose",
    "docker_compose_file": open("docker-compose.yaml").read(),
    "kms_enabled": True,
    "gateway_enabled": True,
    "public_logs": False,
    "public_sysinfo": False,
    "allowed_envs": [],
    "no_instance_id": False,
    "secure_time": True,
    # "pre_launch_script": "...",  # Optional: script that runs before containers start
}

with open("app-compose.json", "w") as f:
    json.dump(app_compose, f, indent=2)
```

**Fields that affect the hash:**
| Field | What it controls |
|-------|-----------------|
| `docker_compose_file` | Your docker-compose.yaml content (embedded as string) |
| `kms_enabled` | Whether the app gets KMS-derived keys |
| `gateway_enabled` | Whether the app gets a TLS endpoint via dstack-gateway |
| `pre_launch_script` | Script that runs before containers start |
| `allowed_envs` | Environment variable names that can be injected |
| Other fields | Various dstack features (logs, sysinfo, secure_time, etc.) |

**Computing the hash:**

The SDK provides deterministic hashing (sorted keys, compact JSON — matches what dstack uses internally):

```bash
pip install dstack-sdk
python -c "
from dstack_sdk import get_compose_hash
import json
compose = json.load(open('app-compose.json'))
print(get_compose_hash(compose))
"
```

**Reference tooling:** The dstack VMM includes a CLI for building app-compose.json: [vmm-cli.py](https://github.com/Dstack-TEE/dstack/blob/main/vmm/src/vmm-cli.py) (see the `compose` subcommand). It's standalone Python 3 — the crypto dependencies are only needed for encrypting environment variables, not for building the compose file.

**What about Phala Cloud?**

Phala Cloud is a convenience layer — it wraps your docker-compose into an app-compose.json for you. But it may inject additional fields like `pre_launch_script`. To verify what's actually deployed:

```bash
# Fetch the complete app-compose.json from a deployed app
phala cvms attestation <app> --json | jq .app_info.tcb_info.app_compose

# Or from a running dstack instance
curl localhost:8090/info
```

See [prelaunch-script](../../prelaunch-script) for the Phala Cloud script source, and [attestation/configid-based](../../attestation/configid-based) for standalone verification.

### ConfigID vs RTMR3

This tutorial uses **ConfigID-based** verification (v0.5.1+), where compose-hash is stored directly in `mr_config_id`. Older dstack versions used **RTMR3 event logs**, where compose-hash was one of several events (app-id, instance-id, key-provider) whose digests were chained together. Trust-center supports both. For details, see [trust-center technical docs](https://docs.phala.com/dstack/trust-center-technical#phase-3:-source-code-verification), [rtmr3-based](https://github.com/Dstack-TEE/dstack-examples/tree/main/attestation/rtmr3-based), and [configid-based](https://github.com/Dstack-TEE/dstack-examples/tree/main/attestation/configid-based).

### Programmatic Verification

The `@phala/dstack-verifier` library handles both approaches automatically:

```typescript
import { VerificationService } from '@phala/dstack-verifier'

const service = new VerificationService()
const result = await service.verify({
  domain: 'myapp.phala.network',
}, {
  hardware: true,
  os: true,
  sourceCode: true,  // Verifies compose-hash
})

if (result.success) {
  console.log('Verification passed')
}
```

See [trust-center](https://github.com/phatcopy/trust-center) for the full verification platform and [Phala docs](https://docs.phala.com/phala-cloud/attestation/trust-center-verification) for detailed reference value explanations.

### Step 2: Verify report_data Binding

The quote's `report_data` field contains `sha256(statement)`. Verify it matches:

```bash
# Extract statement from response and hash it
cat response.json | jq -c '.statement' | tr -d '\n' | shasum -a 256

# Compare with reportDataHash in response
cat response.json | jq -r '.reportDataHash'
```

If they match, the statement is exactly what the TEE produced.

### Step 3: Verify TLS Fingerprint

The `tlsFingerprint` in the statement is the SHA-256 fingerprint of the API server's certificate. You can verify it matches CoinGecko's real certificate:

```bash
# Get CoinGecko's current certificate fingerprint
echo | openssl s_client -connect api.coingecko.com:443 2>/dev/null | \
  openssl x509 -fingerprint -sha256 -noout

# Compare with statement.tlsFingerprint
cat response.json | jq -r '.statement.tlsFingerprint'
```

---

## Critical Thinking: The Auditor's Perspective

> *This section appears throughout the tutorial. Each chapter examines a different trust assumption.*

### The Fundamental Question

As an auditor, your job is to answer: **"Does the deployed system behave according to the source code I reviewed?"**

TEE attestation helps, but only partially. The quote proves *some code* is running in isolated hardware. It gives you hashes. But hashes of what?

```
┌─────────────────────────────────────────────────────────────────┐
│                    The Reference Value Problem                  │
│                                                                 │
│   What you audit:     Source code, Dockerfile, docker-compose  │
│   What quote gives:   compose-hash = 0x392b8a1f...             │
│                                                                 │
│   The gap:  Can you compute 0x392b8a1f from what you audited?  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Trust Layers

Every TEE app has a trust stack. At each layer, ask: *"Can I compute the reference value myself?"*

| Layer | What You're Trusting | How to Verify |
|-------|---------------------|---------------|
| Hardware | Intel TDX is secure | Intel's attestation infrastructure |
| Firmware | No backdoors in BIOS/firmware | Platform vendor (out of scope for dstack) |
| OS | Dstack boots what it claims | [Reproducibly build meta-dstack](https://github.com/Dstack-TEE/meta-dstack) |
| App | Code matches what was audited | [Build app-compose.json locally](#building-app-composejson-locally) |

Dstack's design goal: every layer should be reproducibly verifiable from source.

### How Auditing Actually Works

An auditor doesn't just read code—they run it. The workflow:

1. **Read source** — Form a mental model of intended behavior
2. **Run locally** — Test that model: "does it actually do X? what happens if Y?"
3. **Conclude** — "This code behaves as I understand it. It's safe."

The auditor's conclusion is based on **what they ran**, not what they read. Reading code is necessary but not sufficient—you have to see it execute.

### The Behavioral Gap Threat

Here's the problem: what the auditor ran locally might differ from what's deployed.

```
┌─────────────────────────────────────────────────────────────────┐
│                    The Behavioral Gap                           │
│                                                                 │
│   Auditor builds locally  →  observes behavior A  →  "safe"    │
│   Production build        →  has behavior B (subtly different) │
│   Attestation proves      →  production runs *something*       │
│                                                                 │
│   The auditor certified behavior A.                            │
│   Production has behavior B.                                    │
│   The audit doesn't apply.                                      │
└─────────────────────────────────────────────────────────────────┘
```

This gap can arise from:
- Different dependency versions resolved at build time
- Timestamps or randomness affecting behavior
- Build environment differences (compiler, OS, architecture)
- Intentional divergence (malicious or accidental)

**The hash question isn't abstract.** When an auditor asks "does my local build produce the same hash as production?"—they're really asking: *"Is my local model of the system actually the production system, or just a similar-looking approximation?"*

### What Reproducibility Actually Provides

Reproducibility closes the behavioral gap. If:
- Auditor builds from source → gets hash X
- Production attestation shows → hash X

Then the auditor's local testing environment **is** the production system. Their conclusions apply. The audit is meaningful.

Without reproducibility, the auditor has two options:
1. **Trust the developer's build** — "I audited something similar, probably fine"
2. **Pull the production image and diff manually** — Tedious, error-prone, incomplete

Neither is satisfactory. Reproducibility makes the audit rigorous.

### The Smart Contract Analogy

Smart contracts solved this problem:
- Source code on Etherscan
- Compiler version specified
- Anyone can recompile and verify the bytecode matches on-chain codehash
- DYOR is actually possible

TEE apps need the same pattern. The attestation is like the on-chain codehash. But without reproducible builds, there's no way to connect it back to auditable source.

### The Upgradeability Question

Verifying the current code isn't enough. An auditor should also ask: **"Can this code change tomorrow?"**

When a dstack app uses KMS (most do), there's an **AppAuth contract** on Base that controls which compose hashes are authorized. This is the upgrade mechanism:

- **Who is the owner?** — The address that can authorize new code versions
- **What's the upgrade history?** — All `addComposeHash()` calls are recorded as events
- **Is it locked?** — Has `disableUpgrades()` been called?
- **Is there a notice period?** — Can users exit before new code activates?

Check the AppAuth contract on [Basescan](https://basescan.org) to see the full history of authorized code versions. Unlike traditional servers where deployments are invisible, every "upgrade" is permanently recorded on-chain.

For DevProof applications, **instant upgrades are a rug vector.** The solution is a timelock — new code must be proposed N days before activation, giving users time to audit and exit. This shifts trust from "trust the operator" to "trust you can exit in time."

See [05-onchain-authorization](../05-onchain-authorization#viewing-upgrade-history) for inspecting upgrade history, and [08-extending-appauth](../08-extending-appauth) for implementing timelocks.

---

**Next:** [02-bitrot-and-reproducibility](../02-bitrot-and-reproducibility) shows how developers can provide the evidence auditors need—and protect against bitrot that breaks verification over time.

---

## Next Steps

- [02-bitrot-and-reproducibility](../02-bitrot-and-reproducibility): Make builds verifiable for auditors
- [03-keys-and-replication](../03-keys-and-replication): Derive persistent keys and sign messages
- [04-gateways-and-tls](../04-gateways-and-tls): Custom domains and TLS

## SDK Reference

- **JS/TS**: `npm install @phala/dstack-sdk` — [docs](https://github.com/Dstack-TEE/dstack/tree/master/sdk/js)
- **Python**: `pip install dstack-sdk` — [docs](https://github.com/Dstack-TEE/dstack/tree/master/sdk/python)

## Files

```
01-attestation-and-reference-values/
├── docker-compose.yaml  # Oracle app (quick-start, non-reproducible)
├── verify.py            # Audit any public app
└── README.md
```
