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

### SDK Options

| Language | Install | Docs |
|----------|---------|------|
| JavaScript/TypeScript | `npm install @phala/dstack-sdk` | [sdk/js](https://github.com/Dstack-TEE/dstack/tree/master/sdk/js) |
| Python | `pip install dstack-sdk` | [sdk/python](https://github.com/Dstack-TEE/dstack/tree/master/sdk/python) |

---

## Tutorial Sections

### Core Tutorial

1. **[01-attestation-and-reference-values](./01-attestation-and-reference-values)** — TEE quotes, measured values, and computing reference hashes
2. **[02-bitrot-and-reproducibility](./02-bitrot-and-reproducibility)** — Deterministic builds that auditors can verify now and later
3. **[03-keys-and-replication](./03-keys-and-replication)** — Persistent keys via KMS and multi-node deployments
4. **[04-gateways-and-tls](./04-gateways-and-tls)** — Self-signed TLS with attestation-bound certificates
5. **[05-onchain-authorization](./05-onchain-authorization)** — AppAuth contracts for on-chain key derivation control
6. **[06-hardening-https](./06-hardening-https)** — OCSP stapling, CRL checking, CT records ([oracle template](https://cloud.phala.network/templates/node-oracle-template))

### Advanced

7. **[07-encryption-freshness](./07-encryption-freshness)** — Encrypted storage, integrity, rollback protection
8. **[08-lightclient](./08-lightclient)** — Verified blockchain state via Helios light client
9. **[09-extending-appauth](./09-extending-appauth)** — Custom authorization contracts (timelocks, NFT-gating, multisig)

---

## References

- [Dstack Documentation](https://docs.phala.com/dstack)
- [Phala Cloud](https://cloud.phala.network)
- [trust-center](https://github.com/Phala-Network/trust-center) — Attestation verification
- [dstack GitHub](https://github.com/Dstack-TEE/dstack)
