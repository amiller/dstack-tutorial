# Extending AppAuth for Checkpoint Verification

## Goal

Extend AppAuth so that light client oracles must prove they used a valid on-chain checkpoint.

## Current KMS Architecture

```
KMS (Rust)
    │
    │ webhook POST /bootAuth/app
    ▼
auth-eth-bun (Bun/TS)
    │
    │ ETH_RPC_URL (untrusted RPC!)
    ▼
Base Contract (0x2f83172A49584C017F2B256F0FB2Dca14126Ba9C)
    │
    │ isAppAllowed(bootInfo)
    ▼
DstackApp.sol
```

**Problem:** auth-eth-bun uses an untrusted RPC to read the Base contract.

## Helios Integration Point

Replace untrusted RPC with Helios in auth-eth-bun:

```typescript
// Current (untrusted):
const client = createPublicClient({ transport: http(rpcUrl) });

// With Helios (verified):
// 1. Start Helios opstack --network base
// 2. Use Helios RPC at localhost:8545
const client = createPublicClient({ transport: http('http://localhost:8545') });
```

## Base Checkpoint = L1 Checkpoint

Base doesn't have its own checkpoint. Helios for Base uses L1:

```
L1 checkpoint (EIP-4788 verifiable)
    → L1 Helios verifies L1 state
    → Read SystemConfig.unsafeSigner from L1
    → Trust Base blocks signed by verified signer
    → Verified Base state
```

So checkpoint verification for Base **must happen on L1**.

## The Cross-Chain Challenge

```
┌─────────────────────────────────────────────────────────────────┐
│                         Base (L2)                                │
│                                                                  │
│  ┌─────────────┐         ┌─────────────┐                        │
│  │   AppAuth   │         │  TeeOracle  │                        │
│  │ (KMS auth)  │         │ (verify +   │                        │
│  │             │         │  fulfill)   │                        │
│  └─────────────┘         └─────────────┘                        │
│        │                       │                                │
│        │ isAppAllowed?         │ verify checkpoint?             │
│        ▼                       ▼                                │
│   Can't query L1          Can't query L1                        │
│   EIP-4788 directly       EIP-4788 directly                     │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 │ Need to bridge
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Ethereum L1                                 │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  BEACON_ROOTS (0x000F3df6D732807Ef1319fB7B8bB8522d0Beac02) │  │
│  │                                                             │  │
│  │  call(timestamp) → beacon_root                              │  │
│  │  (valid for ~27 hours)                                      │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Options

### Option A: L1Block + State Proof

Base's L1Block predeploy gives us L1 block hashes, but not beacon roots directly.

However, we could:
1. Get L1 block hash from Base's L1Block
2. Provide Merkle proof that BEACON_ROOTS storage contains the checkpoint
3. Verify the proof on Base

**Pros:** Fully on-chain, no external dependencies
**Cons:** Complex, requires implementing MPT proof verification in Solidity

### Option B: Deploy Verification on L1

Keep KMS/AppAuth on Base, but deploy a checkpoint registry on L1:

```
Base                              Ethereum L1
┌─────────────┐                  ┌─────────────────────────┐
│  TeeOracle  │                  │  CheckpointRegistry     │
│             │ ──verify call──▶ │                         │
│             │                  │  registerCheckpoint()   │
│             │                  │  verifyCheckpoint()     │
└─────────────┘                  └─────────────────────────┘
```

**Pros:** Direct EIP-4788 access on L1
**Cons:** Cross-chain calls add latency and complexity

### Option C: Oracle Submits Checkpoint Proof to Base

The light client oracle:
1. Queries EIP-4788 on L1 (from within TEE)
2. Signs a claim including: checkpoint_root, verify_timestamp, block_hash
3. Submits to Base with the attestation

Base contract verifies:
- TEE attestation (signature chain)
- The checkpoint was valid at the claimed timestamp (trust TEE verified it)

**Pros:** Simple, works today
**Cons:** Trust in TEE's EIP-4788 check (but that's the point of TEE)

### Option D: Beacon Root Oracle on Base

Deploy a simple oracle that posts L1 beacon roots to Base:

```solidity
contract BeaconRootOracle {
    mapping(uint256 => bytes32) public beaconRoots;  // timestamp → root

    // Posted by relayer (could be permissioned or permissionless)
    function postRoot(uint256 timestamp, bytes32 root, bytes proof) external;

    // Used by TeeOracle to verify checkpoints
    function verifyCheckpoint(uint256 timestamp, bytes32 root) view returns (bool);
}
```

**Pros:** Simple integration on Base
**Cons:** Requires separate relayer infrastructure

## Recommended Approach: Option C (TEE-Verified)

For the tutorial, Option C is most practical:

1. **TEE verifies checkpoint on L1** (already implemented in 07-lightclient)
2. **Claim includes verification proof** (`checkpoint_verify_timestamp`)
3. **AppAuth trusts TEE's verification** (the composeHash ensures correct code ran)

The key insight: If you trust the TEE ran the correct code (verified via composeHash), you can trust it verified EIP-4788 correctly. The `checkpoint_verify_timestamp` is included for transparency.

## Extending AppAuth

For future work, AppAuth could check:

```solidity
struct AppBootInfo {
    // ... existing fields ...
    bytes32 checkpointRoot;        // NEW: beacon checkpoint used
    uint256 checkpointTimestamp;   // NEW: EIP-4788 verification timestamp
}

function isAppAllowed(AppBootInfo calldata bootInfo) external view returns (bool, string) {
    // Existing checks...
    if (!allowedComposeHashes[bootInfo.composeHash])
        return (false, "Compose hash not allowed");

    // NEW: Verify checkpoint if provided
    if (bootInfo.checkpointRoot != bytes32(0)) {
        // Option C: Trust TEE verified it (no on-chain check needed)
        // Option D: Check against BeaconRootOracle
        // bytes32 expectedRoot = beaconRootOracle.getRoot(bootInfo.checkpointTimestamp);
        // if (expectedRoot != bootInfo.checkpointRoot)
        //     return (false, "Invalid checkpoint");
    }

    return (true, "");
}
```

## Implementation TODO

1. [ ] Add `checkpointRoot` and `checkpointTimestamp` to oracle claims
2. [ ] Create example TeeOracle that verifies checkpoint in claim
3. [ ] (Optional) Deploy BeaconRootOracle on Base for on-chain verification
4. [ ] Document the trust model (TEE verification vs on-chain verification)

## Trust Model Comparison

| Approach | What verifies checkpoint? | Trust assumption |
|----------|---------------------------|------------------|
| Current (08) | TEE queries EIP-4788 | Trust TEE + correct code |
| Option C | TEE queries EIP-4788, includes in claim | Trust TEE + correct code |
| Option D | Base contract checks BeaconRootOracle | Trust relayer + L1 finality |
| Option A | Base contract verifies state proof | Trust L1 finality only |

For DevProof applications, Option C is sufficient: the composeHash ensures the TEE ran code that correctly verified EIP-4788. The claim is transparent for auditing.
