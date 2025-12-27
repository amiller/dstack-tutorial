# Tutorial 07: Encryption, Integrity, and Freshness

> **Status**: This is an advanced tutorial, work in progress.

Protect persistent data with encryption and detect rollback attacks.

## The Problem

TEE apps often need persistent storage (databases, files). But storage lives outside the TEE:

```
┌─────────────────┐     ┌─────────────────┐
│      TEE        │────▶│   External DB   │
│  (trusted)      │     │  (untrusted)    │
└─────────────────┘     └─────────────────┘
```

An attacker (or malicious operator) could:
1. **Read data** — if stored unencrypted
2. **Modify data** — if no integrity checks
3. **Rollback data** — restore old state to replay transactions

## Encryption with Derived Keys

Use KMS-derived keys to encrypt data at rest:

```javascript
import { DstackClient } from '@phala/dstack-sdk'
import { createCipheriv, createDecipheriv, randomBytes } from 'crypto'

const client = new DstackClient()
const { key } = await client.getKey('/encryption/db')

function encrypt(plaintext) {
  const iv = randomBytes(16)
  const cipher = createCipheriv('aes-256-gcm', key.slice(0, 32), iv)
  const encrypted = Buffer.concat([cipher.update(plaintext), cipher.final()])
  const tag = cipher.getAuthTag()
  return { iv, encrypted, tag }
}
```

This ensures only this TEE app can decrypt the data.

## Integrity

AES-GCM provides authenticated encryption — tampering is detected:

```javascript
function decrypt({ iv, encrypted, tag }) {
  const decipher = createDecipheriv('aes-256-gcm', key.slice(0, 32), iv)
  decipher.setAuthTag(tag)
  return Buffer.concat([decipher.update(encrypted), decipher.final()])
  // Throws if data was tampered
}
```

## Freshness (Rollback Protection)

Encryption and integrity don't prevent rollback attacks. If an attacker restores an old database snapshot, the TEE can't tell.

### Approaches

| Approach | Trade-off |
|----------|-----------|
| **Monotonic counter** | Requires trusted counter storage (e.g., on-chain) |
| **Light client checkpoint** | Anchor state to blockchain block number |
| **Merkle tree on-chain** | Store state root on-chain, verify freshness |
| **Multi-party replication** | Multiple TEEs cross-check state |

### Example: On-Chain State Root

```javascript
// After each state change, post the root hash on-chain
const stateRoot = computeMerkleRoot(database)
await contract.updateStateRoot(stateRoot)

// On startup, verify current state matches on-chain root
const onChainRoot = await contract.getStateRoot()
if (computeMerkleRoot(database) !== onChainRoot) {
  throw new Error('State rollback detected')
}
```

## Access Pattern Leakage

Even with encryption, access patterns leak information:
- Which records are accessed
- Access frequency and timing
- Size of records

Mitigations:
- ORAM (Oblivious RAM) — expensive but hides access patterns
- Dummy accesses — add noise
- Batch operations — access patterns less granular

## Next Steps

- [08-lightclient](../08-lightclient): Use light client for freshness anchoring
- [09-extending-appauth](../09-extending-appauth): Custom authorization policies

## References

- [Intel SGX Sealed Storage](https://www.intel.com/content/www/us/en/developer/articles/technical/introduction-to-intel-sgx-sealing.html)
- [ORAM overview](https://en.wikipedia.org/wiki/Oblivious_RAM)
