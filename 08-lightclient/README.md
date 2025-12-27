# Tutorial 08: Light Client Oracle

Read verified Ethereum state inside a TEE without trusting an RPC provider.

## What it does

```
┌─────────────────────────────────────────────────────────────────┐
│                         TEE                                      │
│                                                                  │
│  ┌─────────┐    ┌──────────┐    ┌─────────┐                     │
│  │ Helios  │───▶│ oracle.py│───▶│  Proof  │                     │
│  │  Light  │    │          │    │  (JSON) │                     │
│  │ Client  │    │ sign +   │    │         │                     │
│  └────┬────┘    │ quote    │    └─────────┘                     │
│       │         └──────────┘                                     │
│       ▼                                                          │
│  Untrusted RPC                                                   │
└───────┬──────────────────────────────────────────────────────────┘
        │
        ▼
  ┌──────────────┐     ┌─────────────────────┐
  │ PublicNode   │     │ beaconcha.in        │
  │ (execution)  │     │ (checkpoint sync)   │
  └──────────────┘     └─────────────────────┘
```

[Helios](https://github.com/a16z/helios) is an Ethereum light client that verifies block headers and state proofs. The TEE:

1. Syncs Helios using a beacon chain checkpoint
2. Queries block data and contract state via verified light client
3. Signs the claim with a KMS-derived key
4. Gets a TDX quote binding `sha256(claim)` to `report_data`

## Why this matters

Unlike [05-onchain-authorization](../05-onchain-authorization) which fetches from off-chain APIs (CoinGecko), this reads directly from Ethereum state. Helios verifies state proofs internally, so you don't need to trust the RPC provider.

Use cases:
- Attested `eth_call` results (token balances, contract state)
- Cross-chain bridges that verify source chain state
- Oracles for L2s that need L1 state proofs

## Run

```bash
docker compose build
docker compose run --rm app
```

With a custom RPC (for `eth_call` state proofs):

```bash
ETH_RPC_URL="https://mainnet.infura.io/v3/YOUR_KEY" docker compose run --rm -e ETH_RPC_URL app
```

## Output

```json
{
  "claim": {
    "type": "lightclient_attestation",
    "network": "mainnet",
    "checkpoint_epoch": 416537,
    "checkpoint_root": "0xbe1360...",
    "block_number": 21492847,
    "block_hash": "0xf180be...",
    "state_root": "0x811128...",
    "call": {
      "to": "0x6b175474e89094c44da98b954eedeac495271d0f",
      "data": "0x18160ddd",
      "result": "0x00000000...db77394bd15356c736ab846"
    }
  },
  "claimHash": "a1b2c3...",
  "signature": "...",
  "pubkey": "...",
  "quote": "BAACAQI..."
}
```

The example queries DAI's `totalSupply()` (`0x18160ddd`) but you can modify the contract call.

## Verification

Two things to verify:

1. **TDX quote** — proves this claim came from a TEE running this code
   → See [01-attestation-and-reference-values](../01-attestation-and-reference-values) for `dcap-qvl` + `dstack-mr` verification

2. **Signature** — signed with KMS-derived key, verifiable on-chain
   → See [05-onchain-authorization](../05-onchain-authorization) for signature chain verification

The `checkpoint_root` can be cross-checked against any beacon chain source (e.g., [beaconcha.in](https://beaconcha.in)).

## Limitations

- **State proofs** require an RPC with `eth_getProof` support. The free PublicNode RPC doesn't support this, so `eth_call` requires setting `ETH_RPC_URL` to Infura/Alchemy.
- **Checkpoint trust**: Initial sync uses beaconcha.in's checkpoint service. The root is included in the claim for cross-verification.

## Files

```
08-lightclient/
├── docker-compose.yaml  # Helios + oracle (self-contained)
└── README.md
```

## Next Steps

- [09-extending-appauth](../09-extending-appauth): Custom authorization contracts
