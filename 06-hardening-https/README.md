# Tutorial 06: Hardening HTTPS

Strengthen TLS verification beyond browser defaults for DevProof applications.

## Why Harden HTTPS?

Browsers trust TLS certificates based on CA signatures alone. For DevProof applications, this isn't enough:

- A CA could be compromised or coerced
- A certificate could be revoked but still accepted (delayed CRL propagation)
- A misissued certificate might not appear in CT logs

TEE oracles fetching external data need stronger guarantees.

## Reference Implementation

The [phala-cloud-oracle-template](https://github.com/Gldywn/phala-cloud-oracle-template) is a production-ready oracle that implements these hardening techniques. It builds on the concepts from this tutorial:

| This tutorial | Oracle template adds |
|---------------|---------------------|
| [01-attestation-and-reference-values](../01-attestation-and-reference-values) | ✓ Same TDX quote binding |
| [03-keys-and-replication](../03-keys-and-replication) | ✓ Same signature chain |
| [04-gateways-and-tls](../04-gateways-and-tls) | ✓ Same TLS basics |
| [05-onchain-authorization](../05-onchain-authorization) | ✓ Same on-chain verification |
| **HTTPS hardening** | OCSP, CRL, CT verification |

For background on the hardening techniques:
- [hardened-https-agent BACKGROUND.md](https://github.com/Gldywn/hardened-https-agent/blob/main/BACKGROUND.md)

## What the Hardened Agent Checks

| Check | What it proves |
|-------|----------------|
| OCSP valid | Certificate wasn't revoked at fetch time |
| CRL checked | No delayed revocation issues |
| CT logged | Certificate was publicly issued (not secret/misissued) |

## Next Steps

- [07-encryption-freshness](../07-encryption-freshness): Advanced — encrypted storage with rollback protection
- [08-lightclient](../08-lightclient): Advanced — verified blockchain state
