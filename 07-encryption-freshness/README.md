# Tutorial 07: Encryption and External Storage

Store encrypted data in external databases using TEE-derived keys.

## The Problem

TEE applications need persistent storage, but all storage is untrusted:

```
┌─────────────────┐     ┌─────────────────┐
│      TEE        │────▶│   External DB   │
│  (trusted)      │     │  (untrusted)    │
└─────────────────┘     └─────────────────┘
        │
        ▼
┌─────────────────┐
│   Local Disk    │
│  (untrusted)    │
└─────────────────┘
```

An external database operator (or malicious disk controller) could:
1. **Read data** — if stored unencrypted
2. **Modify data** — if no integrity checks
3. **Rollback data** — restore old state to replay transactions

## Threat Model: Disk vs External DB

| Environment | Rollback Protection |
|-------------|---------------------|
| **Phala Cloud** | Disk rollback not possible (operator doesn't control disk) |
| **Self-hosted bare metal** | Disk rollback is in threat model |
| **External database** | Always assume rollback is possible |

For DevProof applications, you must assume the operator can rollback state — even if running on Phala Cloud, you might migrate to bare metal later.

## The Pattern: Encrypt Before Storing

Use `getKey()` to derive a deterministic encryption key, then encrypt all records:

```python
from dstack_sdk import DstackClient
from nacl.secret import SecretBox

client = DstackClient()
result = client.get_key("/myapp/db", "encryption")
key = result.decode_key()[:32]  # 32 bytes for SecretBox

box = SecretBox(key)
ciphertext = box.encrypt(plaintext)  # nonce + ciphertext + auth tag
plaintext = box.decrypt(ciphertext)  # fails if tampered
```

**What you get:**
- **Confidentiality**: Database operator can't read your data
- **Integrity**: Tampering is detected (authenticated encryption)

**What you DON'T get:**
- **Freshness**: Operator can replay old valid ciphertext

## Freshness

Authenticated encryption doesn't prevent rollback attacks. If an attacker restores an old database row (with valid ciphertext from a previous state), the TEE decrypts it successfully and can't tell.

Solutions for freshness anchoring:
- On-chain monotonic counter (see [08-lightclient](../08-lightclient))
- Merkle tree root stored on-chain
- Multi-TEE consensus on state

This tutorial focuses on the encryption pattern. Freshness is addressed by combining with [08-lightclient](../08-lightclient).

## Try It

This demo stores encrypted notes in an external Postgres database.

### Option A: Local Test (CI-friendly)

Uses a local postgres container as the "external" database:

```bash
pip install -r requirements.txt
phala simulator start
./test_local.sh
```

### Option B: With Neon (real external DB)

1. Create free account at [neon.tech](https://neon.tech)
2. Create a project and copy the connection string

```bash
phala simulator start
docker compose build
docker run --rm --network=host \
  -e DATABASE_URL="postgres://user:pass@ep-xxx.neon.tech/db?sslmode=require" \
  -v ~/.phala-cloud/simulator/0.5.3/dstack.sock:/var/run/dstack.sock \
  07-encryption-freshness-app
```

In another terminal:
```bash
python3 test_local.py
```

## How It Works

The app exposes a simple key-value store:

```bash
# Store a note (encrypted in postgres)
curl -X POST http://localhost:8080/notes/mykey \
  -H "Content-Type: application/json" \
  -d '{"content": "secret message"}'

# Retrieve (decrypted in TEE)
curl http://localhost:8080/notes/mykey

# List all keys
curl http://localhost:8080/notes
```

What happens:
1. App derives encryption key from KMS: `getKey("/notes", "encryption")`
2. On write: encrypts content with pynacl SecretBox, stores ciphertext in postgres
3. On read: fetches ciphertext, decrypts in TEE, returns plaintext

The database only ever sees encrypted bytes.

## Files

```
07-encryption-freshness/
├── app.py                # Flask app with pynacl encryption
├── docker-compose.yaml   # TEE app definition
├── test_local.sh         # Spins up external postgres + runs tests
├── test_local.py         # Test script
├── requirements.txt      # Python dependencies
└── README.md
```

## Security Considerations

### Key Derivation
The encryption key is derived from `getKey("/notes", "encryption")`. This means:
- Same app (same compose hash) always gets the same key
- Different apps get different keys
- Key survives restarts

### What's NOT Protected
- **Access patterns**: Database sees which keys are accessed and when
- **Record sizes**: Ciphertext length reveals plaintext length
- **Rollback**: Old valid ciphertext decrypts successfully

### Production Hardening
- Use unique nonces (pynacl SecretBox handles this automatically)
- Consider padding to hide record sizes
- Combine with freshness mechanism for rollback protection

## Next Steps

- [08-lightclient](../08-lightclient): Use blockchain for freshness anchoring
