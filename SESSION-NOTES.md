# Tutorial Session Notes - 2025-12-23

## What Was Created

### tutorial/01-attestation-oracle/
Merged tutorial covering:
- **Oracle app**: Fetches BTC price from CoinGecko, captures TLS fingerprint, binds to TDX quote via report_data
- **4 verification options**:
  - A: Hosted (trust.phala.network)
  - B: Local script (attest.sh from attestation/configid-based)
  - C: Programmatic (trust-center API)
  - D: Python script (verify_full.py included)
- **Key concepts explained**:
  - ConfigID-based verification (v0.5.1+) - compose-hash in mr_config_id
  - app-compose.json manifest (includes pre_launch_script)
  - trust-center vs attest.sh differences
  - Complete verification chain: hardware → OS → compose → report_data → TLS fingerprint

### tutorial/02-persistence-and-kms/
- Explains `getKey()` for deterministic key derivation
- KMS holds root keys, derives child keys per path
- Same key across restarts/migrations
- Example: persistent wallet address

### tutorial/03-gateway-and-ingress/
- Short README linking to custom-domain/dstack-ingress
- Explains certificate evidence chain (quote.json → sha256sum.txt → cert.pem)
- When to use default gateway vs dstack-ingress

### tutorial/04-upgrades/
- Extends `AppAuth.sol` with custom authorization logic
- Covers `IAppAuth` interface and `AppBootInfo` struct
- Three extension examples:
  - NFT-gated clusters (1 NFT = 1 node)
  - Timelock upgrades (delay before compose hash activation)
  - Multi-sig approval (threshold of signers)
- References [dstack-nft-cluster](https://github.com/Account-Link/dstack-nft-cluster) as real-world example
- Full `AppBootInfo` field reference for custom policies

### Main README updated
- Added Tutorials section linking all 4 tutorials with descriptions
- Positioned above Use Cases section

## Key Technical Decisions

1. **ConfigID-based verification** (not RTMR3 event chain)
   - Simpler: mr_config_id = "01" + sha256(app-compose.json) padded to 96 chars
   - No event log replay needed

2. **trust-center is hybrid**
   - Uses Phala Cloud API for app discovery
   - Runs verification (dcap-qvl, dstack-mr) locally
   - Downloads OS images from GitHub

3. **Pre-launch script matters**
   - Included in compose-hash
   - Must audit full app-compose.json, not just docker-compose.yaml
   - Fetch via `phala cvms attestation <app>` or trust-center

4. **Verification tools are open source**
   - dcap-qvl: github.com/Phala-Network/dcap-qvl (Rust)
   - dstack-mr: github.com/kvinwang/dstack-mr (Go)
   - dstack OS: github.com/Dstack-TEE/meta-dstack (Yocto)

## Files Modified/Created

- tutorial/01-attestation-oracle/docker-compose.yaml (oracle app)
- tutorial/01-attestation-oracle/README.md (merged tutorial)
- tutorial/01-attestation-oracle/verify_full.py (from old 01-attestation)
- tutorial/02-persistence-and-kms/README.md
- tutorial/03-gateway-and-ingress/README.md
- tutorial/04-upgrades/README.md (AppAuth customization)
- README.md (added Tutorials section, updated quick-start to use tutorial)

## Removed

- tutorial/01-attestation/ (merged into 01-attestation-oracle)
- attestation-with-sdk/ (subsumed by tutorial/01-attestation-oracle)

## References Used

- refs/trust-center/ - verification implementation
- refs/primus-network-startup/ - example of dstack deployment
- attestation/configid-based/ - standalone verification script
- custom-domain/dstack-ingress/ - TLS/custom domain solution
