# Tutorial 09: Custom Authorization and On-Chain Due Diligence

Extend AppAuth with custom authorization logic, including timelock patterns for code upgrades.

## Prerequisites

Complete [05-onchain-authorization](../05-onchain-authorization) first to understand AppAuth basics.

## Overview

The default `phala deploy` creates an AppAuth that only allows a single device. For multi-node deployments or custom authorization logic, you need to deploy the contract yourself.

This tutorial covers:
- **Timelock upgrades** — notice period before new code activates
- Multi-node with `allowAnyDevice=true`
- Owner-controlled device/hash whitelisting
- Custom AppAuth contracts (NFT-gated, multi-sig)

## On-Chain Due Diligence: The Exit Guarantee

The most important pattern in this tutorial is the **timelock for compose hash upgrades**.

### The Problem

With instant `addComposeHash()`, the operator can push malicious code with no warning:

```
Operator calls addComposeHash(malicious) → Instantly active → Users rugged
```

Users must trust the operator won't rug them. That's not devproof.

### The Solution: Notice Period

A timelock transforms the trust model. New code must be announced N days before activation:

```
Operator calls proposeComposeHash(newHash)
    → Wait period begins (visible on-chain)
    → Users can audit the new code (compose hash → deterministic build)
    → Users can EXIT before activation if they disagree
    → Anyone calls activateComposeHash(newHash) after delay
```

### The Key Insight

Trust shifts from **"trust the operator"** to **"trust you can exit in time"**.

This is devproof: users don't need to trust anyone, they just need to monitor and react. The blockchain enforces the notice period — the operator cannot bypass it.

### Use Cases

- **Light client oracles** ([08-lightclient](../08-lightclient)): Users can trust code changes are announced
- **Multi-node clusters**: Operators can verify proposed code before their nodes run it
- **DeFi integrations**: Protocols can pause integrations if bad code is proposed

See [TIMELOCK_APPAUTH_PLAN.md](./TIMELOCK_APPAUTH_PLAN.md) for implementation details.

Related work: [Nerla's demo](https://github.com/njeans/dstack/tree/update-demo/demo)

## Multi-Node with allowAnyDevice

Deploy with `allowAnyDevice=true` so any TEE with the correct compose hash can join without per-device whitelisting.

### Deploy Primary Node

```bash
export PRIVATE_KEY="0x..."
python3 deploy_with_contract.py
```

Output:
```
Deploying CVM with allowAnyDevice=true
============================================================
Compose File Name: tee-oracle-shared (determines compose_hash)
  -> All replicas must use this same compose_file.name!

Step 1: Provisioning CVM resources...
  Compose Hash: 0x392b8a1f...
Step 2: Deploying AppAuth contract with allowAnyDevice=true...
  App ID: 0xc96d55b03ede924c89154348be9dcffd52304af0
Step 3: Creating CVM...

SUCCESS! Save this for deploying replicas:
  APP_ID=0xc96d55b03ede924c89154348be9dcffd52304af0
  COMPOSE_HASH=0x392b8a1f...
```

### Deploy Replicas

Edit `deploy_replica.py` with the APP_ID from above, then:

```bash
python3 deploy_replica.py
```

Both nodes now derive the same key:
```
Node 1: Oracle signer: 0x7a3B...  (same!)
Node 2: Oracle signer: 0x7a3B...  (same!)
```

### How It Works

```
┌─────────────────────────────────────────────────────────────┐
│              AppAuth Contract (allowAnyDevice=true)         │
│                                                             │
│  allowedComposeHashes[0x392b...] = true                     │
│  allowAnyDevice = true                                      │
│                                                             │
│  isAppAllowed(bootInfo):                                    │
│    if composeHash in allowedComposeHashes → ALLOW           │
│    (device ID doesn't matter)                               │
└─────────────────────────────────────────────────────────────┘
          │                           │
          ▼                           ▼
    ┌──────────┐               ┌──────────┐
    │  Node 1  │               │  Node 2  │
    │  prod5   │               │  prod9   │
    └──────────┘               └──────────┘
          │                           │
          │  getKey("/oracle")        │  getKey("/oracle")
          ▼                           ▼
    Same derived key            Same derived key
```

**The compose_file.name trick:** All replicas must use the same `compose_file.name` (not CVM name) to get the same compose_hash. See `COMPOSE_FILE_NAME` in `deploy_with_contract.py` and `deploy_replica.py`.

## The AppAuth Interface

Every authorization contract implements `IAppAuth`:

```solidity
interface IAppAuth {
    struct AppBootInfo {
        bytes32 appId;
        bytes32 instanceId;
        bytes32 composeHash;
        bytes32 deviceId;
        bytes32 mrAggregated;
        bytes32 mrSystem;
        bytes32 osImageHash;
        string tcbStatus;
        string[] advisoryIds;
    }

    function isAppAllowed(AppBootInfo calldata bootInfo)
        external view returns (bool isAllowed, string memory reason);
}
```

The KMS calls `isAppAllowed()` when an app requests keys. Your contract decides if the app should receive them based on whatever logic you implement.

## Base Implementation: DstackApp.sol

The default contract checks two things:

1. **Compose hash whitelist** — Is `bootInfo.composeHash` in the allowed set?
2. **Device whitelist** — Is `bootInfo.deviceId` allowed (or `allowAnyDevice` enabled)?

```solidity
function isAppAllowed(AppBootInfo calldata bootInfo)
    external view returns (bool, string memory)
{
    if (!allowedComposeHashes[bootInfo.composeHash])
        return (false, "Compose hash not allowed");

    if (!allowAnyDevice && !allowedDevices[bootInfo.deviceId])
        return (false, "Device not allowed");

    return (true, "");
}
```

Source: [Dstack-TEE/dstack/kms/auth-eth/contracts](https://github.com/Dstack-TEE/dstack/tree/master/kms/auth-eth/contracts)

## Extending with Custom Logic

### Example: NFT-Gated Cluster

The [dstack-nft-cluster](https://github.com/Account-Link/dstack-nft-cluster) project extends authorization with NFT membership:

```solidity
contract DstackMembershipNFT is ERC721, IAppAuth {
    mapping(uint256 => bytes32) public tokenToInstanceId;
    mapping(bytes32 => string) public instanceToConnectionUrl;

    function isAppAllowed(AppBootInfo calldata bootInfo)
        external view returns (bool, string memory)
    {
        // Check if instanceId is registered to an NFT
        if (!isInstanceRegistered(bootInfo.instanceId))
            return (false, "Instance not registered to NFT");

        // Verify signature chain from KMS
        if (!verifySignatureChain(bootInfo))
            return (false, "Invalid signature chain");

        return (true, "");
    }

    function registerInstance(uint256 tokenId, string calldata name) external {
        require(ownerOf(tokenId) == msg.sender, "Not token owner");
        // ...
    }
}
```

This creates a "1 NFT = 1 node" model where token holders control cluster participation.

### Example: Timelock Upgrades (Implemented)

See [TimelockAppAuth.sol](./TimelockAppAuth.sol) for the full implementation with tests.

```bash
# Run the tests
forge test -vv
```

Key methods:
- `proposeComposeHash(hash)` — starts notice period (owner only)
- `activateComposeHash(hash)` — activates after delay (anyone can call)
- `cancelProposal(hash)` — cancels pending proposal (owner only)
- `activatesAt(hash)` — returns when a proposal can be activated

### Example: Multi-Sig Approval

Require multiple signers before adding compose hashes:

```solidity
contract MultiSigAppAuth is DstackApp {
    uint256 public threshold;
    mapping(bytes32 => mapping(address => bool)) public approvals;
    mapping(bytes32 => uint256) public approvalCount;

    function approve(bytes32 hash) external {
        require(isSigner[msg.sender], "Not a signer");
        require(!approvals[hash][msg.sender], "Already approved");
        approvals[hash][msg.sender] = true;
        approvalCount[hash]++;

        if (approvalCount[hash] >= threshold)
            allowedComposeHashes[hash] = true;
    }
}
```

## The AppBootInfo Fields

| Field | Description |
|-------|-------------|
| `appId` | Hash of app configuration (compose-hash) |
| `instanceId` | Unique identifier for this running instance |
| `composeHash` | SHA-256 of app-compose.json manifest |
| `deviceId` | Hardware identifier of the TEE |
| `mrAggregated` | Combined measurement of firmware + OS |
| `mrSystem` | System-level measurement |
| `osImageHash` | Hash of the dstack OS image |
| `tcbStatus` | Intel TCB status (UpToDate, OutOfDate, etc.) |
| `advisoryIds` | List of applicable Intel security advisories |

Use these fields to implement sophisticated authorization policies. For example, reject apps running on outdated firmware:

```solidity
if (keccak256(bytes(bootInfo.tcbStatus)) != keccak256("UpToDate"))
    return (false, "TCB not up to date");
```

## Owner-Controlled Whitelisting

For production deployments where you want explicit control over which devices and code versions can run, use the base `DstackApp` owner functions.

### Adding Devices

```bash
# Using cast
cast send $APP_AUTH_ADDRESS "addDevice(bytes32)" $DEVICE_ID \
  --private-key "$PRIVATE_KEY" --rpc-url https://mainnet.base.org

# Or use the helper script
python3 add_device.py
```

### Adding Compose Hashes (Upgrades)

When you change your `docker-compose.yaml`, you get a new compose hash that must be whitelisted:

```bash
# Using cast
cast send $APP_AUTH_ADDRESS "addComposeHash(bytes32)" $NEW_COMPOSE_HASH \
  --private-key "$PRIVATE_KEY" --rpc-url https://mainnet.base.org

# Or use the helper script
python3 add_compose_hash.py
```

**Note:** The `compose_file.name` field (not CVM name) determines the compose hash. Keep this consistent across deployments. See [05-onchain-authorization](../05-onchain-authorization) for details.

### Files

```
09-extending-appauth/
├── TimelockAppAuth.sol        # Timelock pattern implementation
├── TimelockAppAuth.t.sol      # Foundry tests (forge test)
├── test_anvil.py              # Integration test (local anvil)
├── deploy_timelock.py         # Deploy TimelockAppAuth to Phala Cloud + Base
├── test_phalacloud.py         # Test timelock on Base mainnet
├── TIMELOCK_APPAUTH_PLAN.md   # Design rationale
├── deploy_with_contract.py    # Deploy with allowAnyDevice=true
├── deploy_replica.py          # Deploy replica using existing appId
├── add_device.py              # Add device to whitelist
├── add_compose_hash.py        # Add compose hash (for upgrades)
└── README.md
```

## Deployment

1. Deploy your custom contract to a supported chain (Base, Ethereum, etc.)
2. Configure the KMS to use your contract address
3. Deploy apps — they'll be authorized via your contract

For Phala Cloud's on-chain KMS, see [Cloud vs On-chain KMS](https://docs.phala.network/phala-cloud/key-management/cloud-vs-onchain-kms).

## References

- [IAppAuth interface](https://github.com/Dstack-TEE/dstack/blob/master/kms/auth-eth/contracts/IAppAuth.sol)
- [DstackApp base contract](https://github.com/Dstack-TEE/dstack/blob/master/kms/auth-eth/contracts/DstackApp.sol)
- [dstack-nft-cluster](https://github.com/Account-Link/dstack-nft-cluster) — NFT-gated authorization example
- [Key Management Protocol](https://docs.phala.network/dstack/design-documents/key-management-protocol)

## Next Steps

- [01-attestation-and-reference-values](../01-attestation-and-reference-values): Understand attestation verification
- [03-keys-and-replication](../03-keys-and-replication): How apps derive keys from KMS
