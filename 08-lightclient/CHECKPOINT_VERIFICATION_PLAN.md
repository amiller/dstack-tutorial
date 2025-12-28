# Light Client Checkpoint Approaches

## How dstack Does It (Default)

dstack-kms uses a **hardcoded checkpoint** without fallback:

```yaml
# From refs/dstack/kms/dstack-app/docker-compose.yaml
helios:
  command: [
    "./target/release/helios",
    "ethereum",
    "--network", "mainnet",
    "--checkpoint", "0xbee4f32f91e62060d2aa41c652f6c69431829cfb09b02ea3cad92f65bd15dcce",
    "--rpc-bind-ip", "0.0.0.0",
    ...
  ]
```

This checkpoint is ~354 days old but still works because beacon nodes retain bootstrap data for **epoch boundary checkpoints** indefinitely.

**Pros:** Simple, stable, no external dependencies at runtime
**Cons:** Cannot be verified on-chain (outside EIP-4788's 27h window)

## Alternative: EIP-4788 Dynamic Verification

For stronger on-chain verifiability, use fresh checkpoints verified via EIP-4788.

## Background

### EIP-4788 Beacon Roots Contract
- Address: `0x000F3df6D732807Ef1319fB7B8bB8522d0Beac02`
- Stores parent beacon block roots in a ring buffer
- Buffer size: 8191 slots (~27 hours at 12s/slot)
- Query: `call(contract, abi.encode(timestamp))` returns 32-byte beacon root

### Helios Light Client
- Can sync from any finalized beacon block root via `--checkpoint <root>`
- Finality on Ethereum takes ~15 minutes (2 epochs)
- Any checkpoint >15 min old should be finalized

## Proposed Flow

```
┌─────────────────────────────────────────────────────────────┐
│                         TEE                                  │
│                                                              │
│  1. Query EIP-4788 for beacon root from N hours ago:        │
│     timestamp = block.timestamp - (N * 3600)                 │
│     root = eth_call(BEACON_ROOTS, timestamp)                 │
│                                                              │
│  2. Start Helios with that checkpoint:                       │
│     helios --checkpoint $root                                │
│                                                              │
│  3. Helios syncs and verifies the chain from checkpoint     │
│                                                              │
│  4. Query verified state via Helios RPC                      │
│                                                              │
│  5. Sign claim including:                                    │
│     - checkpoint_timestamp                                   │
│     - checkpoint_root                                        │
│     - block_number, block_hash, state_root                   │
│     - TEE quote binding claim hash                           │
└─────────────────────────────────────────────────────────────┘
```

## Verification Model

Anyone can verify:
1. **Checkpoint validity**: Call `BEACON_ROOTS.call(checkpoint_timestamp)` and check it matches `checkpoint_root`
2. **TEE attestation**: Verify TDX quote contains hash of claim
3. **Code integrity**: Verify composeHash matches expected oracle code

## Key Insight

The checkpoint doesn't need to be in AppAuth's `isAppAllowed` check because:
- The composeHash verifies the TEE is running code that does the checkpoint verification
- The claim includes the checkpoint for transparency
- Verifiers can independently check the checkpoint was valid

## Testing Results

### 12-hour old checkpoint - FAILED
```
Timestamp: 1766844803 (12h ago)
Root: 0x1856e9f57122c0c50d6990574a4778c863279580e0da605f47adb740267ba852
Error: "LC bootstrap unavailable"
```
Beacon nodes prune bootstrap data - they don't serve sync committee data for old checkpoints.

### Arbitrary 1-2 hour old checkpoints - FAILED
Same issue - beacon nodes don't serve bootstrap for arbitrary old checkpoints.

### Current Finalized Checkpoint - SUCCESS ✓
```
Root: 0x930ad14f309033b986b7cd1bafac87f8f563b43f36c57397f51c7b924b6d60af
Slot: 13338944 (epoch 416842)
EIP-4788 verification timestamp: 1766891363 (slot+1)
```

## Key Insight: Use Current Finalized, Verify On-Chain

The solution is NOT to pick an arbitrary old checkpoint from EIP-4788. Instead:

1. **Get current finalized checkpoint** from beaconcha.in (or any checkpoint service)
2. **Verify it exists in EIP-4788** by querying at `timestamp(slot+1)`
3. **Use that verified checkpoint** with Helios

This works because:
- Current finalized checkpoints have bootstrap data available
- EIP-4788 stores parent_beacon_block_root, so slot N's root appears at slot N+1's timestamp
- The verification timestamp can be included in claims for on-chain verification

## Implementation - COMPLETE ✓

1. [x] `get_checkpoint.py`: Fetches finalized checkpoint, verifies via EIP-4788
2. [x] `run.sh`: Passes verified checkpoint to Helios
3. [x] `oracle.py`: Includes `checkpoint_verify_timestamp` in claim
4. [x] Verified full flow works with simulator

## Verification Model

Anyone can verify the checkpoint was valid:
```solidity
bytes32 root = BEACON_ROOTS.call(abi.encode(checkpoint_verify_timestamp));
require(root == claim.checkpoint_root, "invalid checkpoint");
```

## References

- EIP-4788: https://eips.ethereum.org/EIPS/eip-4788
- Helios: https://github.com/a16z/helios
- Beacon roots contract deployed at Dencun upgrade (March 2024)
