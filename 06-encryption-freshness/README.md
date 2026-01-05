# Tutorial 06: Encryption and External Storage

Store encrypted data in external databases using TEE-derived keys.

## Why This Matters for DevProof

**Encryption alone doesn't make an app DevProof.** A malicious operator can't read encrypted data, but they can still:
- **Observe access patterns** — which records are accessed and when
- **Rollback state** — restore old data to manipulate outcomes
- **Correlate activity** — link encrypted records to external events

For DevProof applications, encryption is necessary but not sufficient. This tutorial covers the encryption pattern; freshness anchoring via [07-lightclient](../07-lightclient) addresses rollback.

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

## Why External Database?

Disk rollback is part of the DevProof threat model — any bare metal deployment could snapshot and restore the disk. Phala Cloud doesn't expose an easy way to do this, but that's an implementation detail, not a security guarantee.

We use an external database in this demo because rollback is obviously possible: you control the database, you can restore yesterday's backup. This makes the threat concrete and testable. The same encryption pattern applies to local disk storage.

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
- On-chain monotonic counter (see [07-lightclient](../07-lightclient))
- Merkle tree root stored on-chain
- Multi-TEE consensus on state

This tutorial focuses on the encryption pattern. Freshness is addressed by combining with [07-lightclient](../07-lightclient).

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
  06-encryption-freshness-app
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

---

## Exercises

### Exercise 1: Inspect encrypted data

Run `./test_local.sh`, then view the raw database:
```bash
docker exec -it postgres psql -U postgres -d notes -c "SELECT * FROM notes;"
```

Is the content readable?

### Exercise 2: Perform a rollback attack

1. Create a note, save its ID
2. Dump the database: `docker exec postgres pg_dump -U postgres notes > backup.sql`
3. Update the note with new content
4. Restore the backup: `docker exec -i postgres psql -U postgres notes < backup.sql`
5. Read the note — what content do you see?

What does this tell you about authenticated encryption vs freshness?

---

## Files

```
06-encryption-freshness/
├── app.py                # Flask app with pynacl encryption
├── docker-compose.yaml   # TEE app definition
├── test_local.sh         # Spins up external postgres + runs tests
├── test_local.py         # Test script
├── requirements.txt      # Python dependencies
└── README.md
```

## Security Considerations

### What Encryption Gives You

| Property | Protected? | Notes |
|----------|------------|-------|
| **Confidentiality** | ✅ | Operator can't read data |
| **Integrity** | ✅ | Tampering detected via auth tag |
| **Freshness** | ❌ | Rollback to old state undetected |
| **Access pattern hiding** | ❌ | Operator sees which keys when |

### DevProof Implications

For a truly DevProof application, consider:

1. **Rollback attacks** — An operator restoring yesterday's database could reverse a withdrawal, replay a settled bet, or undo a governance vote. Anchor state freshness on-chain (see [07-lightclient](../07-lightclient)).

2. **Access pattern leakage** — Even without reading data, an operator observing "user A accessed record X, then user B accessed record X" can infer relationships. For high-stakes privacy, consider ORAM or batched access patterns.

3. **Correlation attacks** — Timing of encrypted writes correlated with external events (blockchain transactions, API calls) can reveal information.

### Key Derivation
The encryption key is derived from `getKey("/notes", "encryption")`:
- Same app (same compose hash) always gets the same key
- Different apps get different keys
- Key survives restarts

## Next Steps

- [07-lightclient](../07-lightclient) — Freshness anchoring via blockchain light client
