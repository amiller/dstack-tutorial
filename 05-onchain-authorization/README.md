# Tutorial 05: On-Chain Authorization

Every dstack app has an **AppAuth contract** on Base that controls which code versions are allowed to run.

## Prerequisites

Complete [03-keys-and-replication](../03-keys-and-replication) first.

## Understanding AppAuth

When a TEE requests keys from the KMS, the KMS calls your AppAuth's `isAppAllowed()` to decide:

```
┌─────────────────────────────────────────────────────────────┐
│                    DstackKms Contract (Base)                │
│                                                             │
│  registerApp(address) ← registers your AppAuth              │
│  isAppAllowed(bootInfo) → delegates to your contract        │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ calls IAppAuth(appId).isAppAllowed(bootInfo)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Your AppAuth Contract (DstackApp)              │
│                                                             │
│  owner: 0x...  ← can add compose hashes                     │
│  allowedComposeHashes[...]                                  │
│  allowedDeviceIds[...]                                      │
│                                                             │
│  isAppAllowed(bootInfo) → checks whitelist                  │
└─────────────────────────────────────────────────────────────┘
```

**Key insight:** The private key you deploy with becomes the **owner** of the AppAuth contract. Only the owner can authorize new code versions.

## Deploying with On-Chain KMS

When you deploy with `--kms-id` and `--private-key`, the CLI creates an AppAuth contract for you:

```bash
phala deploy -n my-oracle -c docker-compose.yaml \
  --kms-id kms-base-prod5 \
  --private-key "$PRIVATE_KEY"
```

This:
1. Deploys an AppAuth contract to Base (owner = your wallet)
2. Registers the initial compose hash
3. Creates the CVM

## Updating Your App

When you change your `docker-compose.yaml` and redeploy, the compose hash changes. The CLI automatically calls `addComposeHash()` on your AppAuth contract:

```bash
# Update existing CVM with new code
phala deploy --cvm-id my-oracle -c docker-compose.yaml \
  --private-key "$PRIVATE_KEY"
```

This:
1. Computes the new compose hash
2. Calls `addComposeHash(newHash)` on your AppAuth contract
3. Updates the CVM with the new compose

**The transaction is signed by your private key** — only the owner can authorize new code.

## Viewing Upgrade History on Basescan

Every `addComposeHash()` and `addDevice()` call emits an event. This creates an **auditable on-chain history** of all authorized code versions.

**View your contract's events:**
```
https://basescan.org/address/<YOUR_APP_AUTH_ADDRESS>#events
```

Example events from a real deployment:

| Block | Method | Event |
|-------|--------|-------|
| 39966824 | `deployAndRegisterApp` | `Initialized` — contract created |
| 39967092 | `addDevice` | `DeviceAdded(0x05c734...)` — new TEE authorized |
| 39967137 | `addComposeHash` | `ComposeHashAdded(0x7070fd...)` — new code version |

**Why this matters:** Users and auditors can verify the complete history of what code was ever authorized. Unlike traditional servers where deployments are invisible, every "upgrade" is permanently recorded on-chain.

### DevProof Upgrades: The Exit Guarantee

On-chain visibility is necessary but not sufficient. With instant `addComposeHash()`, the operator can still push malicious code with no warning:

```
Operator calls addComposeHash(malicious) → Instantly active → Users rugged
```

For true DevProof, use a **timelock** — new code must be announced N days before activation, giving users time to audit and exit. See [08-extending-appauth](../08-extending-appauth) for `TimelockAppAuth`, which enforces a notice period on-chain.

## Finding Your AppAuth Address

```bash
phala cvms get my-oracle --json | jq -r '.contract_address'
```

Or check the Phala Cloud dashboard for your CVM.

## Events Reference

From [DstackApp.sol](https://github.com/dstack-tee/dstack/blob/main/kms/auth-eth/contracts/DstackApp.sol):

| Event | When Emitted |
|-------|--------------|
| `ComposeHashAdded(bytes32)` | New code version authorized |
| `ComposeHashRemoved(bytes32)` | Code version revoked |
| `DeviceAdded(bytes32)` | New TEE device authorized |
| `DeviceRemoved(bytes32)` | Device revoked |
| `AllowAnyDeviceSet(bool)` | Device policy changed |
| `UpgradesDisabled()` | Owner permanently locked upgrades |

## Oracle Request/Fulfill Contract

`TeeOracle.sol` implements a simple request/fulfill pattern where anyone can:
1. Post a price request with an ETH reward
2. The TEE oracle signs the current price
3. Anyone can fulfill the request with a valid oracle signature and claim the reward

```solidity
// Post a request with ETH reward
function request() external payable returns (uint256 requestId);

// Fulfill with verified oracle signature, claim reward
function fulfill(
    uint256 requestId,
    uint256 price,
    uint256 priceTimestamp,
    OracleProof calldata proof
) external;
```

The `fulfill` function verifies the complete DStack signature chain before releasing the reward.

## Test with Anvil

Test the request/fulfill cycle locally:

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
TeeOracle Request/Fulfill Test
============================================================
Anvil block: 0
Fetching oracle price...
  Price: $97234.56
  Timestamp: 1735321234
  App ID: ea549f02e1a25fabd1cb788380e033ec5461b2ff
Deploying TeeOracle.sol...
  Contract: 0x5FbDB2315678afecb367f032d93F642f64180aa3

Posting price request with 0.01 ETH reward...
  Request ID: 0
  Reward: 0.01 ETH

Fulfilling request...
  Fulfilled price: $97234.56
  Reward received: 0.0100 ETH

============================================================
SUCCESS: Oracle request/fulfill cycle complete
  - Posted request with ETH reward
  - Oracle signed price verified on-chain
  - Reward claimed by fulfiller
```

---

## Exercises

### Exercise 1: View upgrade history

Find an app's AppAuth contract on [Basescan](https://basescan.org) and view its event history. How many `ComposeHashAdded` events are there?

### Exercise 2: Run the Foundry tests

```bash
forge test -vv
```

What does `testUpdatePrice` verify?

### Exercise 3: Trace signature verification

In `TeeOracle.sol`, find the `_verifySignature` function. What prevents a replay attack where someone resubmits the same signed price?

---

## Files

```
05-onchain-authorization/
├── TeeOracle.sol              # Request/fulfill oracle with signature verification
├── TeeOracle.t.sol            # Forge unit tests (run: forge test)
├── foundry.toml               # Foundry config
├── test_anvil.py              # Integration test with live oracle
├── test_local.py              # Test signature verification
├── test_phalacloud.py         # Test on Phala Cloud
├── docker-compose.yaml        # Oracle app
├── requirements.txt
└── README.md
```

## Running Tests

**Forge tests** (no oracle needed):
```bash
forge install foundry-rs/forge-std  # first time only
forge test
```

**Anvil integration test** (requires oracle running):
```bash
anvil &
phala simulator start
docker compose up -d
python3 test_anvil.py
```

## Contract Addresses

| Contract | Address |
|----------|---------|
| DstackKms (Base) | `0x2f83172A49584C017F2B256F0FB2Dca14126Ba9C` |
| KMS Root (Simulator) | `0x8f2cF602C9695b23130367ed78d8F557554de7C5` |

## Next Steps

- [06-encryption-freshness](../06-encryption-freshness): Encrypted external storage
- [08-extending-appauth](../08-extending-appauth): Custom authorization contracts, multi-node with allowAnyDevice, owner-controlled whitelisting

## References

- [DstackKms.sol](https://github.com/dstack-tee/dstack/blob/main/kms/auth-eth/contracts/DstackKms.sol)
- [DstackApp.sol](https://github.com/dstack-tee/dstack/blob/main/kms/auth-eth/contracts/DstackApp.sol)
