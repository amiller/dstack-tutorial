# Tutorial 07: Light Client Oracle

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

For a deeper dive into why light clients and TEEs are a natural fit, see [Understanding Helios and Exploring Light Clients' Affinity to TEEs](https://heytdep.github.io/post/31/post.html) by heytdep.

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
    "checkpoint_root": "0xbee4f32f...",
    "block_number": 24108441,
    "block_hash": "0x7cdc872d...",
    "state_root": "0x352afa4f..."
  },
  "claimHash": "3e0a038c...",
  "signature": "...",
  "pubkey": "...",
  "quote": "BAACAQI..."
}
```

The example queries DAI's `totalSupply()` (`0x18160ddd`) but you can modify the contract call.

## Verification

Two things to verify:

1. **TDX quote** — proves this claim came from a TEE running this code
   → See [01-attestation-and-reference-values](../01-attestation-and-reference-values) for verification

2. **Signature** — signed with KMS-derived key, verifiable on-chain
   → See [05-onchain-authorization](../05-onchain-authorization) for signature chain verification

## Checkpoint Approach

This example uses a **hardcoded checkpoint** (same as dstack-kms):

```
0xbee4f32f91e62060d2aa41c652f6c69431829cfb09b02ea3cad92f65bd15dcce
```

This is an epoch boundary checkpoint. Beacon nodes retain bootstrap data for these indefinitely, so no fallback URL is needed.

See [CHECKPOINT_VERIFICATION_PLAN.md](./CHECKPOINT_VERIFICATION_PLAN.md) for alternative approaches including dynamic EIP-4788 verification.

## Limitations

- **State proofs** require an RPC with `eth_getProof` support. Free RPCs may not support this for historical state.
- **Checkpoint trust**: The hardcoded checkpoint cannot be verified on-chain (outside EIP-4788's 27h window). Trust derives from the attested code (composeHash).

## Files

```
07-lightclient/
├── docker-compose.yaml              # Helios + oracle (self-contained)
├── CHECKPOINT_VERIFICATION_PLAN.md  # EIP-4788 implementation notes
└── README.md
```

## Next Steps

- [08-extending-appauth](../08-extending-appauth): Custom authorization contracts
