# Tutorial 09: Upgrades and Custom Authorization

Extend the `AppAuth` contract with custom authorization logic for your dstack apps.

## Overview

dstack uses on-chain contracts to authorize which apps can access the KMS. The base `DstackApp.sol` contract provides simple compose-hash and device-id whitelisting. You can extend this with custom logic:

- NFT-gated membership (1 NFT = 1 authorized node)
- Timelock governance (delay before new compose hashes activate)
- Multi-sig approval
- On-chain voting

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

### Example: Timelock Upgrades

Add a delay before new compose hashes become active:

```solidity
contract TimelockAppAuth is DstackApp {
    uint256 public constant DELAY = 2 days;
    mapping(bytes32 => uint256) public pendingComposeHashes;

    function proposeComposeHash(bytes32 hash) external onlyOwner {
        pendingComposeHashes[hash] = block.timestamp + DELAY;
    }

    function activateComposeHash(bytes32 hash) external {
        require(pendingComposeHashes[hash] != 0, "Not proposed");
        require(block.timestamp >= pendingComposeHashes[hash], "Too early");
        allowedComposeHashes[hash] = true;
        delete pendingComposeHashes[hash];
    }
}
```

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
