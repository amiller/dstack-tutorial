# Tutorial 03: Keys and Replication

Derive persistent keys that survive restarts and produce verifiable signatures.

## The Problem

TEE memory is wiped on restart. If your app generates a private key at startup, it gets a new key every time — breaking wallets, signatures, and any persistent identity.

## The Solution: `getKey()`

The dstack SDK's `getKey()` derives deterministic keys from KMS:

```javascript
import { DstackClient } from '@phala/dstack-sdk'

const client = new DstackClient()
const result = await client.getKey('/oracle', 'ethereum')

const privateKey = '0x' + Buffer.from(result.key).toString('hex').slice(0, 64)
```

The derived key is:
- **Deterministic**: Same path → same key, every restart
- **Unique to your app**: Different apps (compose hashes) get different keys
- **Verifiable**: Signature chain proves the key came from KMS

## Signature Chain

The KMS returns a **signature chain** proving derivation:

```
KMS Root (known on-chain)
    │
    │ signs: "dstack-kms-issued:" + appId + appPubkey
    ▼
App Key (recovered from kmsSignature)
    │
    │ signs: "ethereum:" + derivedPubkeyHex
    ▼
Derived Key → signs your messages
```

```javascript
const result = await client.getKey('/oracle', 'ethereum')

result.key                    // Your derived key bytes
result.signature_chain[0]     // App signature: appKey signs derivedPubkey
result.signature_chain[1]     // KMS signature: kmsRoot signs appPubkey
```

## Try It

```bash
pip install -r requirements.txt
phala simulator start

docker compose build
docker compose run --rm -p 8080:8080 \
  -v ~/.phala-cloud/simulator/0.5.3/dstack.sock:/var/run/dstack.sock \
  app
```

In another terminal:

```bash
python3 test_local.py
```

Output:
```
TEE Oracle Signature Chain Verification
============================================================
Oracle URL: http://localhost:8080
KMS Root: 0x8f2cF602C9695b23130367ed78d8F557554de7C5

Fetching from oracle...
Got price: $97234.0
Source: api.coingecko.com

Verifying Signature Chain
==================================================
App ID: 0x...
Derived Pubkey: 02a1b2c3d4e5f6...

Step 1: App signature over derived key
  App Address: 0x...

Step 2: KMS signature over app key
  Recovered KMS: 0x8f2cF602C9695b23130367ed78d8F557554de7C5
  Expected KMS:  0x8f2cF602C9695b23130367ed78d8F557554de7C5
  OK: KMS signature verified

Step 3: Message signature
  Recovered signer: 0x...
  Expected signer:  0x...
  OK: Message signature verified

============================================================
All verifications passed:
  - KMS signed the app key
  - App key signed the derived key
  - Derived key signed the oracle message
```

## Verifying the Signature Chain

The verification steps:

1. **App signature** — Recover the app public key from `appSignature` over the message `"{purpose}:{derivedPubkeyHex}"`

2. **KMS signature** — Recover the KMS signer from `kmsSignature` over the message `"dstack-kms-issued:" + appId + appPubkeyCompressed`. Compare against known KMS root.

3. **Message signature** — Recover the signer from the message signature. Compare against address derived from `derivedPubkey`.

If all three pass, the signature chain is valid: the message was signed by a key derived from KMS for this specific app.

## On-Chain Verification

The same verification can run in a smart contract. See [05-onchain-authorization](../05-onchain-authorization) for `TeeOracle.sol` which implements:

```solidity
function verify(
    bytes32 messageHash,
    bytes calldata messageSignature,
    bytes calldata appSignature,
    bytes calldata kmsSignature,
    bytes calldata derivedCompressedPubkey,
    bytes calldata appCompressedPubkey,
    string calldata purpose
) public view returns (bool isValid)
```

## Key Paths

Use paths to organize multiple keys:

```javascript
await client.getKey('/wallet/main')      // Main wallet
await client.getKey('/wallet/fees')      // Fee payer
await client.getKey('/signing/oracle')   // Oracle signatures
```

## Multi-Node Deployment

Multiple TEE nodes can derive the **same key** if they share the same `appId`. This enables redundancy and load balancing while maintaining a single signing identity.

```
┌─────────────────────────────────────────────────────────────┐
│              AppAuth Contract (allowAnyDevice=true)         │
│                                                             │
│  allowedComposeHashes[0x392b...] = true                     │
│  allowAnyDevice = true                                      │
└─────────────────────────────────────────────────────────────┘
          │                           │
          ▼                           ▼
    ┌──────────┐               ┌──────────┐
    │  Node 1  │               │  Node 2  │
    └──────────┘               └──────────┘
          │                           │
          │  getKey("/oracle")        │  getKey("/oracle")
          ▼                           ▼
    Same derived key            Same derived key
```

For multi-node deployment with `allowAnyDevice=true`, see [08-extending-appauth](../08-extending-appauth).

## Files

```
03-keys-and-replication/
├── docker-compose.yaml       # Oracle with signing
├── test_local.py             # Signature chain verification
├── requirements.txt          # Python dependencies
└── README.md
```

## Next Steps

- [04-gateways-and-tls](../04-gateways-and-tls): Custom domains and TLS
- [05-onchain-authorization](../05-onchain-authorization): On-chain AppAuth and upgrade history

## References

- [Key Management Protocol](https://docs.phala.network/dstack/design-documents/key-management-protocol)
- [DstackKms contract](https://github.com/dstack-tee/dstack/blob/main/kms/auth-eth/contracts/DstackKms.sol)
