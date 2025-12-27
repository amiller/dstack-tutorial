# Implementation Notes: Self-Join Oracle

Notes from implementing multi-node oracle deployment with shared signing keys.

## Challenges Encountered

### 1. CLI `--custom-app-id` Flag is Disabled

The `--custom-app-id` flag exists in the CLI's help text but **the implementation is commented out** in the phala-cloud-cli source (`src/commands/deploy/index.ts` lines 126-162):

```typescript
// TODO: remove customAppId for now
// if (customAppId) { ... }  // ALL COMMENTED OUT
```

Every CLI deployment creates a new AppAuth contract, making self-join impossible via CLI alone. This is why we use direct API calls in `deploy_with_contract.py` and `deploy_replica.py`.

### 2. API Key Decryption

The CLI encrypts stored API keys (`~/.phala-cloud/api-key`) with AES-256-CBC using a machine-specific key:

```python
parts = f"{hostname}|{platform}|{arch}|{cpu_model}|{username}"
key = hashlib.sha256(parts.encode()).digest()
```

**Gotcha**: Python `platform.machine()` returns `x86_64`, but Node.js `os.arch()` returns `x64`. The scripts include this conversion.

### 3. allowAnyDevice Defaults to False

First replica failed at "requesting app keys" because the AppAuth contract only allowed the original device (prod5). Required redeploying with `allowAnyDevice=true` via direct contract call.

### 4. compose_hash Includes CVM Name

Each CVM name produces a different compose_hash. Replicas fail with "Compose hash not allowed" until you call `addComposeHash()` on the AppAuth contract for each replica's hash.

**Workaround**: After deploying a replica, get its compose_hash and register it:

```python
from web3 import Web3
w3 = Web3(Web3.HTTPProvider("https://mainnet.base.org"))
app_auth = w3.eth.contract(address=APP_AUTH_ADDRESS, abi=APP_AUTH_ABI)
tx = app_auth.functions.addComposeHash(compose_hash_bytes).build_transaction(...)
```

### 5. Image Version Matters

Base KMS clusters showed "No available resources" with `v0.5.4-dev`. Using `dstack-0.5.4` (non-dev image) worked.

## Future CLI Improvements Needed

1. Re-enable `--custom-app-id` flag
2. Add `--allow-any-device` flag for AppAuth deployment
3. Add command to register additional compose hashes (`phala app add-compose-hash`)

## Successful Deployment

After resolving these issues, both oracles (prod5 and prod9) share identical:
- appId: `5a367973f645a11328d5b80fc226e3cb7436f78e`
- signerAddress: `0x7B83657880051cD6782E1D7fFFf3e6bd54f06853`
- derivedPubkey: `0x0323c9da9e831c9a677a92597a95c40bd7e7fe723d215763ef70874ae5dd660404`

Both produce identical signatures for the same input, enabling oracle redundancy.
