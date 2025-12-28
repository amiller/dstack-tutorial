# Dstack Tutorial: Building DevProof Applications

This tutorial teaches you to build **DevProof** (or "unruggable") applications using Dstack — apps where even the developer can't cheat users.

## Why DevProof?

**DevProof** is a threat model where we assume the developer themselves might be malicious, and design the system so they *can't* betray users even if they wanted to.

This is what smart contracts and DeFi aspire to, but TEEs let us apply it to practical, general-purpose code — not just on-chain logic.

| Application | DevProof property |
|-------------|-------------------|
| Oracle for prediction markets | Developer can't manipulate how bets settle |
| Verifiable credentials (zkTLS) | Developer can't forge credentials |
| User consent collection | Developer can prove they collected N consents |
| Data handling | Developer can prove no user data was exposed |

### Security Stages

[ERC-733](https://draft.erc733.org) (draft) defines a maturity model for TEE+EVM applications:

| Stage | Name | Description |
|-------|------|-------------|
| **0** | Prototype / Ruggable | TEE is used but trust chains are incomplete. Developer or host remains a single point of failure. |
| **1** | **Dev-Proof** | Developer cannot unilaterally alter, censor, or exfiltrate data without notice. TEE integrity is cryptographically verifiable. |
| **2** | Decentralized TEE Network | Multiple enclaves/vendors share control. No single party can censor or upgrade unilaterally. |
| **3** | Trustless TEE | Enclaves coordinate through cryptographic verification (TEE×ZK, multi-vendor cross-attestation). |

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

### The Trust Model Shift

Traditional TEE apps: *"Trust me, it runs in a TEE"*

DevProof TEE apps: *"Don't trust me — verify the code, check the upgrade history"*

This mirrors how DeFi protocols handle governance. Projects like Compound and Uniswap use [Governor contracts with timelocks](https://docs.openzeppelin.com/contracts/4.x/governance) — proposed changes must wait before execution, giving stakeholders time to review. The same pattern applies to TEE code upgrades.

The building blocks:

1. **Verifiable code** — Auditors can confirm source matches deployed hash ([01](./01-attestation-and-reference-values), [02](./02-bitrot-and-reproducibility))
2. **On-chain upgrade history** — Every code change is recorded as an event ([05](./05-onchain-authorization))
3. **Governance controls** — Timelocks, multisig, or custom policies for upgrades ([08](./08-extending-appauth))

## Why This Tutorial?

**Running in a TEE doesn't automatically make your app DevProof.** If you follow typical Dstack guides, you'll get an ordinary server where you (the admin) can still "rug" your users. The app runs in a TEE, but the developer retains backdoors.

DevProof design requires intentional effort:
- Users must be able to verify what code is running (not just "some TEE code")
- Builds must be reproducible so auditors can confirm the hash
- Upgrade mechanisms must be visible on-chain
- The verification path must be documented and accessible

Smart contracts solved these problems through open source, verifiable builds, on-chain codehash, and transparent upgrade policies. TEE apps need similar patterns — but the techniques are non-obvious and scattered across documentation. This tutorial brings them together.

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
| Phala CLI | Simulator + deploy | `npm install -g @phala/cloud-cli` |
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

### Core Tutorial

1. **[01-attestation-and-reference-values](./01-attestation-and-reference-values)** — TEE quotes, reference hashes, and the auditor's perspective
2. **[02-bitrot-and-reproducibility](./02-bitrot-and-reproducibility)** — Deterministic builds that auditors can verify now and later
3. **[03-keys-and-replication](./03-keys-and-replication)** — Persistent keys via KMS and multi-node deployments
4. **[04-gateways-and-tls](./04-gateways-and-tls)** — Self-signed TLS with attestation-bound certificates
5. **[05-onchain-authorization](./05-onchain-authorization)** — On-chain upgrade history, transparent code changes

### Advanced

6. **[06-encryption-freshness](./06-encryption-freshness)** — Encrypted storage, integrity, rollback protection
7. **[07-lightclient](./07-lightclient)** — Verified blockchain state via Helios light client
8. **[08-extending-appauth](./08-extending-appauth)** — **Exit guarantees**: timelocks, multi-node, custom authorization

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
