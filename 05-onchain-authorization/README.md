# Tutorial 05: On-Chain Authorization

Controlled multi-node deployment and custom authorization contracts.

## Prerequisites

Complete [03-keys-and-replication](../03-keys-and-replication) first. That tutorial covers:
- Signature chain verification
- Basic multi-node with `allowAnyDevice=true`

This tutorial covers **controlled** multi-node setups where the owner explicitly approves devices.

## Understanding AppAuth

Every dstack app has an **AppAuth contract** on Base. When a TEE requests keys, KMS calls your AppAuth's `isAppAllowed()` to decide.

```
┌─────────────────────────────────────────────────────────────┐
│                    DstackKms Contract (Base)                 │
│                                                             │
│  registerApp(address) ← registers your AppAuth              │
│  isAppAllowed(bootInfo) → delegates to your contract        │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ calls IAppAuth(appId).isAppAllowed(bootInfo)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Your AppAuth Contract (DstackApp)               │
│                                                             │
│  owner: 0x...  ← can add devices/hashes                     │
│  allowedDeviceIds[...]                                      │
│  allowedComposeHashes[...]                                  │
│  allowAnyDevice: true/false                                 │
│                                                             │
│  isAppAllowed(bootInfo) → checks whitelist                  │
└─────────────────────────────────────────────────────────────┘
```

**Key insight:** The private key you deploy with becomes the **owner** of the AppAuth contract. The owner controls which devices and compose hashes are allowed.

## Deployment Options

### Option 1: allowAnyDevice (Recommended for Multi-Node)

Deploy with `allowAnyDevice=true` so any TEE can join without per-device whitelisting:

```bash
python3 deploy_with_contract.py
```

This creates AppAuth with:
- `owner` = address derived from PRIVATE_KEY
- `allowAnyDevice = true` ← any TEE device can join
- `allowedComposeHashes[hash] = true` ← only this code version

**The compose_file.name trick:** All replicas must use the same `compose_file.name` (not CVM name) to get the same compose_hash. See `COMPOSE_FILE_NAME` in `deploy_with_contract.py` and `deploy_replica.py`.

```python
# deploy_with_contract.py and deploy_replica.py both use:
COMPOSE_FILE_NAME = "tee-oracle-shared"  # Determines compose_hash!
```

Deploy replicas:
```bash
# Edit REPLICA_NAME in deploy_replica.py, then:
python3 deploy_replica.py
```

### Option 2: Single Device (CLI Default)

```bash
phala deploy -n my-oracle -c docker-compose.yaml \
  --kms-id kms-base-prod5 \
  --private-key "$PRIVATE_KEY"
```

Creates AppAuth with:
- `allowAnyDevice = false`
- Only this specific device whitelisted

### Option 3: Owner-Controlled Whitelisting

For production deployments where the owner explicitly approves each device and code version, see [09-extending-appauth](../09-extending-appauth).

### Option 4: Custom AppAuth Contract

Deploy your own contract implementing `IAppAuth`:

```solidity
interface IAppAuth {
    function isAppAllowed(AppBootInfo calldata bootInfo)
        external view returns (bool isAllowed, string memory reason);
}
```

Then register it:
```solidity
DstackKms(KMS_ADDRESS).registerApp(yourContract);
```

**Examples:** NFT-gated, DAO-controlled, time-locked, multi-sig. See [09-extending-appauth](../09-extending-appauth).

## DstackApp Owner Functions

```solidity
function addDevice(bytes32 deviceId) external onlyOwner;
function removeDevice(bytes32 deviceId) external onlyOwner;
function addComposeHash(bytes32 composeHash) external onlyOwner;
function removeComposeHash(bytes32 composeHash) external onlyOwner;
function setAllowAnyDevice(bool allow) external onlyOwner;
function disableUpgrades() external onlyOwner;  // Permanent!
```

## Viewing Upgrade History

As discussed in [01-attestation-and-reference-values](../01-attestation-and-reference-values#the-upgradeability-question), verifying the current code isn't enough—auditors need to understand the upgrade policy and history.

Every `addComposeHash()`, `addDevice()`, and other owner action emits an event. This creates an auditable on-chain history of all authorized code versions.

**View on Basescan:**

```
https://basescan.org/address/<APP_AUTH_ADDRESS>#events
```

Example events you'll see:
- `ComposeHashAdded(bytes32 composeHash)` — new code version authorized
- `ComposeHashRemoved(bytes32 composeHash)` — code version revoked
- `DeviceAdded(bytes32 deviceId)` — new TEE device authorized
- `AllowAnyDeviceChanged(bool allow)` — device policy changed

**Why this matters:** Users and auditors can verify the complete history of what code was ever authorized to run. Unlike traditional servers where deployments are invisible, every "upgrade" is permanently recorded on-chain.

**Query with cast:**

```bash
# Get all ComposeHashAdded events
cast logs --from-block 0 --address $APP_AUTH_ADDRESS \
  "ComposeHashAdded(bytes32)" --rpc-url https://mainnet.base.org
```

## On-Chain Verification Contract

`TeeOracle.sol` verifies the signature chain from [03-keys-and-replication](../03-keys-and-replication) on-chain:

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

## Test with Anvil

Test the full on-chain verification locally:

```bash
# Terminal 1: Start anvil
anvil &

# Terminal 2: Start oracle (with simulator)
phala simulator start
docker compose run --rm -p 8080:8080 \
  -v ~/.phala-cloud/simulator/0.5.3/dstack.sock:/var/run/dstack.sock app

# Terminal 3: Run anvil test
pip install -r requirements.txt
python3 test_anvil.py
```

Output:
```
TeeOracle Anvil Test
============================================================
Oracle: http://localhost:8080
Anvil: http://localhost:8545
KMS Root: 0x8f2cF602C9695b23130367ed78d8F557554de7C5

Anvil connected, block: 0
Fetching from oracle...
  Price: $87436
  App ID: ea549f02e1a25fabd1cb788380e033ec5461b2ff
  App Pubkey: 02b85cceca0c02d878f0...
Deploying TeeOracle.sol...
  Contract: 0x5FbDB2315678afecb367f032d93F642f64180aa3
Calling verify() on-chain...

============================================================
SUCCESS: On-chain verification passed
  - KMS signature verified
  - App signature verified
  - Message signature verified
```

## Files

```
05-onchain-authorization/
├── TeeOracle.sol              # On-chain signature verification
├── foundry.toml               # Foundry config (via-ir for stack depth)
├── deploy_with_contract.py    # Deploy with allowAnyDevice=true
├── deploy_replica.py          # Deploy replica using existing appId
├── test_anvil.py              # Test with local anvil
├── test_phalacloud.py         # Test on Phala Cloud
├── docker-compose.yaml        # Oracle app (same as 03)
├── requirements.txt
└── README.md
```

## Contract Addresses

| Contract | Address |
|----------|---------|
| DstackKms (Base) | `0x2f83172A49584C017F2B256F0FB2Dca14126Ba9C` |
| KMS Root (Simulator) | `0x8f2cF602C9695b23130367ed78d8F557554de7C5` |

## IAppAuth Interface

From [dstack/kms/auth-eth/contracts/IAppAuth.sol](https://github.com/dstack-tee/dstack/blob/main/kms/auth-eth/contracts/IAppAuth.sol):

```solidity
struct AppBootInfo {
    address appId;
    bytes32 composeHash;
    address instanceId;
    bytes32 deviceId;
    bytes32 mrAggregated;
    bytes32 mrSystem;
    bytes32 osImageHash;
    string tcbStatus;
    string[] advisoryIds;
}

function isAppAllowed(AppBootInfo calldata bootInfo)
    external view returns (bool isAllowed, string memory reason);
```

## Next Steps

- [06-hardening-https](../06-hardening-https): Strengthen TLS verification
- [09-extending-appauth](../09-extending-appauth): Custom authorization contracts

## References

- [DstackKms.sol](https://github.com/dstack-tee/dstack/blob/main/kms/auth-eth/contracts/DstackKms.sol)
- [DstackApp.sol](https://github.com/dstack-tee/dstack/blob/main/kms/auth-eth/contracts/DstackApp.sol)
- [NOTES.md](NOTES.md)
