# TimelockAppAuth: On-Chain Due Diligence for Code Upgrades

> **Related work**: Nerla's demo implementation: https://github.com/njeans/dstack/tree/update-demo/demo

## Motivation

The default AppAuth allows the owner to instantly whitelist new compose hashes. This means:
- Operator can push malicious code with no warning
- Users must trust the operator won't rug them

A **notice period** transforms this trust model:
- New compose hashes are announced N days before activation
- Stakeholders can audit the new code (it's deterministic from compose hash)
- Users can exit before bad code runs
- Trust shifts from "trust the operator" to "trust you can exit in time"

This pattern is common in Ethereum governance:
- [OpenZeppelin TimelockController](https://docs.openzeppelin.com/contracts/4.x/api/governance#TimelockController)
- Upgrade controllers for proxy contracts
- DAO proposal delays

## Contract Design

```solidity
contract TimelockAppAuth is DstackApp {
    uint256 public noticePeriod;  // 2 minutes for demo, 2 days for production

    // hash → timestamp when it becomes valid (0 = not proposed)
    mapping(bytes32 => uint256) public proposedAt;

    event ComposeHashProposed(bytes32 indexed hash, uint256 activatesAt);
    event ComposeHashActivated(bytes32 indexed hash);
    event ComposeHashCancelled(bytes32 indexed hash);

    function proposeComposeHash(bytes32 hash) external onlyOwner {
        require(proposedAt[hash] == 0, "Already proposed");
        require(!allowedComposeHashes[hash], "Already active");
        proposedAt[hash] = block.timestamp;
        emit ComposeHashProposed(hash, block.timestamp + NOTICE_PERIOD);
    }

    function activateComposeHash(bytes32 hash) external {
        require(proposedAt[hash] != 0, "Not proposed");
        require(block.timestamp >= proposedAt[hash] + noticePeriod, "Notice period not elapsed");
        allowedComposeHashes[hash] = true;
        delete proposedAt[hash];
        emit ComposeHashActivated(hash);
    }

    function cancelProposal(bytes32 hash) external onlyOwner {
        require(proposedAt[hash] != 0, "Not proposed");
        delete proposedAt[hash];
        emit ComposeHashCancelled(hash);
    }

    // Override to prevent instant addition
    function addComposeHash(bytes32 hash) public override onlyOwner {
        revert("Use proposeComposeHash instead");
    }
}
```

## Key Differences from OpenZeppelin TimelockController

| Aspect | TimelockController | TimelockAppAuth |
|--------|-------------------|-----------------|
| Scope | Any contract call | Just compose hashes |
| Roles | Proposer, Executor, Admin | Just Owner |
| Activation | Executor role required | Anyone can activate |
| Complexity | High (batches, predecessor chains) | Minimal |

We keep it simple because:
1. Only one action type (whitelist compose hash)
2. Activation is permissionless (transparency)
3. Owner retains cancel authority (safety valve)

## Trust Model

```
Without timelock:
  Owner calls addComposeHash() → Instantly active → Users trust operator

With timelock:
  Owner calls proposeComposeHash()
    → 2 day wait (auditable on-chain)
    → Anyone calls activateComposeHash()
    → Users trust: "I can exit in 2 days if I see bad code proposed"
```

## Use Cases

1. **Light Client Oracle (07-lightclient)**: Users of the oracle can trust that code changes are announced. If a malicious update is proposed, they can stop relying on the oracle before it activates.

2. **Multi-node clusters**: Node operators can verify proposed code changes before their nodes start running new code.

3. **DeFi integrations**: Protocols integrating with TEE oracles can monitor for code changes and pause integrations if needed.

## Implementation

- [TimelockAppAuth.sol](./TimelockAppAuth.sol) — standalone contract (2 minute demo delay)
- [TimelockAppAuth.t.sol](./TimelockAppAuth.t.sol) — 12 Foundry tests

```bash
forge test -vvv
```

## Reference

The hardcoded checkpoint approach (same as dstack core):
```
refs/dstack/kms/dstack-app/docker-compose.yaml:23
--checkpoint 0xbee4f32f91e62060d2aa41c652f6c69431829cfb09b02ea3cad92f65bd15dcce
```

This is orthogonal to the timelock pattern - the checkpoint is about light client bootstrapping, the timelock is about governance of code upgrades.
