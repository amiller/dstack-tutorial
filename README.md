# Dstack Tutorial: Building DevProof Applications

This tutorial teaches you to build **DevProof** (or "unruggable") applications using Dstack — apps where even the developer can't cheat users.

## Why DevProof?

**DevProof** is a threat model where we assume the developer themselves might be malicious, and design the system so they *can't* betray users even if they wanted to.

This notion is very close to what smart contracts and DeFi are designed around. TEEs also let us apply it to practical, general-purpose code.

### Security ≠ DevProof

Most TEE documentation focuses on *security*: proving hardware is genuine, code wasn't tampered with, measurements match. These are necessary but not sufficient.

| Security asks | DevProof asks |
|---------------|---------------|
| Can an attacker break in? | Can the *developer* cheat users? |
| Is the hardware genuine? | Who controls code upgrades? |
| Does the code match the hash? | Can users audit what the hash means? |
| Is the quote signed by Intel? | What's the upgrade notice period? |
| Does Trust Center say ✅? | Can users exit if they disagree? |

**A TEE app can pass every security check while remaining fully ruggable.** Stage 0 apps get ✅ on Trust Center. DevProof requires additional properties that security verification doesn't check.

### Trust Anchors

Every system has **trust anchors** — entities you must trust. TEE apps typically require trusting:

| Trust Anchor | Security concern | DevProof concern |
|--------------|------------------|------------------|
| Hardware (Intel) | Is TDX backdoored? | (same) |
| Cloud provider | Is infrastructure compromised? | Can verify independently |
| KMS operator | Are keys leaked? | Onchain KMS removes this |
| **App developer** | Is code authenticated? | **Can they rug users?** |

Security focuses on *authentication* (is this the right developer?). DevProof focuses on *removing the developer as a trust anchor entirely* — users don't need to trust the developer because they can verify and exit.

This tutorial specifically targets removing the developer trust anchor. Other trust anchors (hardware vendor, cloud provider) can also be reduced — see [08-extending-appauth](./08-extending-appauth) for multi-vendor patterns.

### Security Stages

[ERC-733](https://draft.erc733.org) (draft) defines a maturity model for TEE+EVM applications:

| Stage | Name | Security | DevProof | Gap |
|-------|------|----------|----------|-----|
| **0** | Ruggable | ✅ Passes | ❌ No | Developer can push updates without notice |
| **1** | **DevProof** | ✅ Passes | ✅ Yes | Upgrade transparency + exit mechanisms |
| **2** | Decentralized | ✅ Passes | ✅ Yes | No single party controls upgrades |
| **3** | Trustless | ✅ Passes | ✅ Yes | Cryptographic multi-vendor verification |

**This tutorial gets you to Stage 1 and partway to Stage 2.** Most TEE apps today are Stage 0 — they run in a TEE but the developer can still rug users. Stage 1 is achievable with intentional design and is the minimum bar for "mainnet-worthy" applications.

#### What this tutorial covers toward Stage 2

| Stage 2 Requirement | Tutorial Coverage | Gap |
|---------------------|-------------------|-----|
| Multi-node deployment | ✅ `allowAnyDevice` in [08](./08-extending-appauth) | — |
| On-chain authorization | ✅ AppAuth contract controls who can join | — |
| Decentralized governance | ⚠️ Timelocks shown; multisig/Governor can layer on | Not demonstrated |
| Multi-vendor TEE | ⚠️ AppAuth pattern is vendor-agnostic | Verification scripts for SEV/Nitro not included |
| Cloud attestation | ❌ | See [Proof of Cloud](https://proofofcloud.org/) working group |
| Permissionless operation | ⚠️ Architecture supports it | Requires open AppAuth policy |

The on-chain authorization pattern ([05](./05-onchain-authorization)) is the key primitive — it's not TDX-specific. Adding AMD SEV or AWS Nitro support means adding verification scripts for those attestation formats, not changing the architecture.

### Dstack's Design Philosophy

Dstack was built for DevProof applications from the start — **"Code is Law" + "Assume Breach"**:

- **Governance-as-code** — Smart contracts control application lifecycle (deployment, updates, deletion), creating immutable audit trails
- **Verifiable, not perfect** — Rather than claiming TEEs are unbreakable, the system designs for recovery and limits exposure windows

## Why This Tutorial?

**Running in a TEE doesn't automatically make your app DevProof.** If you follow typical guides, you'll get an ordinary server where you (the admin) can still "rug" your users. The app runs in a TEE, but the developer retains backdoors.

DevProof design requires intentional effort:
- Users must be able to verify what code is running (not just "some TEE code")
- Builds must be reproducible so auditors can confirm the hash
- Upgrade mechanisms must be visible on-chain
- The verification path must be documented and accessible

Smart contracts solved these problems through open source, verifiable builds, on-chain codehash, and transparent upgrade policies. TEE apps need similar patterns — the techniques exist in dstack but are scattered across documentation. This tutorial brings them together.

### Phala Cloud Docs: Security Foundation

[Phala Cloud's attestation docs](https://docs.phala.com/phala-cloud/attestation) cover the *security* foundation that DevProof builds on:

| Topic | Phala Doc | This Tutorial |
|-------|-----------|---------------|
| Hardware/quote verification | [Verify the Platform](https://docs.phala.com/phala-cloud/attestation/verify-the-platform) | Assumed baseline |
| Compose-hash basics | [Verify Your Application](https://docs.phala.com/phala-cloud/attestation/verify-your-application) | [02-bitrot](./02-bitrot-and-reproducibility) extends with reproducibility |
| Trust Center reports | [Attestation Overview](https://docs.phala.com/phala-cloud/attestation) | What Trust Center *doesn't* check |
| KMS and key derivation | Verify the Platform § Key Management | [03-keys](./03-keys-and-replication) adds trust model clarity |

**DevProof gaps** (not covered in Phala docs):
- Upgrade transparency → [05-onchain-authorization](./05-onchain-authorization)
- Exit guarantees and timelocks → [08-extending-appauth](./08-extending-appauth)
- Reproducible builds as requirement → [02-bitrot-and-reproducibility](./02-bitrot-and-reproducibility)
- Verification from user/auditor perspective → [01-attestation](./01-attestation-and-reference-values)

## Running Example: TEE Oracle

Throughout this tutorial, we build a **price oracle** for prediction markets:
1. Fetches prices from external APIs
2. Proves the data came from a specific TLS server
3. Signs results with TEE-derived keys
4. Verifiable on-chain

Each section adds a layer until we have a fully DevProof oracle.

---

## Development Environment

**You can complete the entire tutorial without TDX hardware.** The simulator provides everything needed to develop and test locally.

### Requirements

| Tool | Purpose | Install |
|------|---------|---------|
| Docker | Run apps | [docker.com](https://docker.com) |
| Phala CLI | Simulator + deploy | `npm install -g phala` |
| Python 3 | Test scripts | System package |
| Foundry | On-chain testing (05) | [getfoundry.sh](https://getfoundry.sh) |

### Local Development (Simulator)

```bash
# Start the simulator (provides mock KMS + attestation)
phala simulator start

# Run any tutorial section
cd 03-keys-and-replication
docker compose build
docker compose run --rm -p 8080:8080 \
  -v ~/.phala-cloud/simulator/0.5.3/dstack.sock:/var/run/dstack.sock \
  app

# Run tests
pip install -r requirements.txt
python3 test_local.py
```

The simulator provides:
- `getKey()` — deterministic key derivation
- `tdxQuote()` — mock attestation quotes
- Signature chains verifiable against simulator KMS root

### On-Chain Testing (Anvil)

For [05-onchain-authorization](./05-onchain-authorization), use anvil for local contract testing:

```bash
anvil &                    # Local Ethereum node
forge create TeeOracle.sol # Deploy verification contract
```

### Production Deployment

```bash
# Phala Cloud (managed TDX)
phala deploy -n my-app -c docker-compose.yaml

# Self-hosted TDX
# See https://docs.phala.com/dstack/local-development
```

> **Note:** A DevProof design minimizes dependency on any single provider. The verification techniques work regardless of where you deploy.

### Remote Debugging

For debugging deployed CVMs on Phala Cloud, you can drop in an SSH service alongside your app. See [00-ssh-debugging](./00-ssh-debugging) for a ready-to-use pattern that gives you shell access to inspect containers, check logs, and debug networking — works with any compose file.

### CI

GitHub Actions runs tests on every push:
- **Foundry Tests** — Solidity unit tests for `TeeOracle.sol`
- **Simulator Tests** — Runs tests for sections 03, 04, 05, and 07 with the phala simulator
- **Anvil Integration** — Full on-chain test: simulator + anvil + oracle contract deployment

### SDK Options

| Language | Install | Docs |
|----------|---------|------|
| JavaScript/TypeScript | `npm install @phala/dstack-sdk` | [sdk/js](https://github.com/Dstack-TEE/dstack/tree/master/sdk/js) |
| Python | `pip install dstack-sdk` | [sdk/python](https://github.com/Dstack-TEE/dstack/tree/master/sdk/python) |

---

## Tutorial Sections

| # | Section | DevProof property |
|---|---------|-------------------|
| 01 | **[attestation-and-reference-values](./01-attestation-and-reference-values)** | Framing verification from the *user/auditor* perspective, not the operator |
| 02 | **[bitrot-and-reproducibility](./02-bitrot-and-reproducibility)** | A hash is meaningless if users can't audit what it represents |
| 03 | **[keys-and-replication](./03-keys-and-replication)** | KMS trust model: who controls the root keys? |
| 04 | **[gateways-and-tls](./04-gateways-and-tls)** | TLS certificates bound to attestation, not operator-controlled |
| 05 | **[onchain-authorization](./05-onchain-authorization)** | Upgrade transparency — without this, all other verification is moot |
| 06 | **[encryption-freshness](./06-encryption-freshness)** | Rollback protection: developer can't restore old state to replay attacks |
| 07 | **[lightclient](./07-lightclient)** | Don't trust external blockchain state — verify it inside TEE |
| 08 | **[extending-appauth](./08-extending-appauth)** | Exit mechanisms: timelocks give users time to leave before malicious upgrades |

---

## Beyond Stage 1: User Opt-Out

This tutorial focuses on Stage 1 (DevProof). For Stage 2+ patterns, see [njeans/dstack opt-out demo](https://github.com/njeans/dstack/tree/update-demo/demo) which demonstrates:

- **Governance voting** on upgrade proposals
- **User opt-out** — users who object can exclude their data from migration
- **Data sovereignty** — opted-out users' data stays with the old version

The opt-out pattern shifts trust from "I can exit in time" to "my data won't follow me without consent." This is a stronger guarantee than timelocks alone and is a key building block for Stage 2 systems.

---

## References

- [ERC-733](https://draft.erc733.org) (draft) — TEE+EVM security stages and design patterns
- [Dstack Documentation](https://docs.phala.com/dstack)
- [Phala Cloud](https://cloud.phala.network)
- [trust-center](https://github.com/Phala-Network/trust-center) — Attestation verification
- [dstack GitHub](https://github.com/Dstack-TEE/dstack)
