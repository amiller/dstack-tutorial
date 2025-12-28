# Tutorial 04: Gateways and TLS

Self-signed TLS with attestation-bound certificates, exposed via ngrok TCP tunnel.

## Prerequisites

Complete [01-attestation-and-reference-values](../01-attestation-and-reference-values) first.

## The Problem

Traditional TLS requires trusting Certificate Authorities. When you connect to `https://example.com`, you're trusting:
- The CA that signed the certificate (could be compromised or coerced)
- Any relay that terminates TLS (sees plaintext)
- DNS resolution (could be hijacked)

For DevProof applications, we want an *additional* trust anchor: the attested code itself.

## Attested TLS

**Attested TLS** doesn't replace CA certificates — it adds attestation verification on top of them.

| Approach | Browser compatible? | Attestation verified? |
|----------|--------------------|-----------------------|
| CA-only TLS | ✓ | ✗ |
| Self-signed + attestation | ✗ (warning) | ✓ |
| **Attested TLS** (CA + attestation) | ✓ | ✓ |

The key insight: **CA certs and attestation serve different purposes.**

- CA certs prove domain ownership (browsers need this)
- Attestation proves the code that holds the private key

With Attested TLS, browsers work normally AND security-conscious clients can verify the cert was generated inside verified TEE code.

**Certificate Transparency bonus:** For domains using CT (most do), you can enumerate all certificates ever issued for that domain. If every cert fingerprint appears in a valid attestation, you have strong assurance no rogue certs exist.

## Two Approaches

This tutorial shows both:

1. **Self-signed + attestation** (simple, requires attestation verification)
2. **Gateway with CA cert** (browser-compatible, gateway is trusted relay)

---

## Approach 1: Self-Signed + Attestation (ngrok TCP)

The TEE generates a self-signed certificate. The fingerprint goes in the attestation. Clients verify the cert matches what's attested.

```
┌────────┐         ┌─────────┐         ┌─────────────────────────┐
│ Client │ ─ TLS ─ │  ngrok  │ ─ TCP ─ │ TEE                     │
│        │         │  (TCP)  │         │ ┌─────────────────────┐ │
│        │         │         │         │ │ Self-signed cert    │ │
│        │         │         │         │ │ Fingerprint in      │ │
│        │         │         │         │ │ attestation         │ │
│        │         │         │         │ └─────────────────────┘ │
└────────┘         └─────────┘         └─────────────────────────┘
          ngrok only sees encrypted bytes
```

### Running with ngrok

**1. Get ngrok auth token**

Sign up at [ngrok.com](https://ngrok.com) (free). TCP tunnels require identity verification (credit card on file, not charged).

*Why does ngrok require verification for TCP?* Because they can't inspect the traffic - it's encrypted end-to-end. This is exactly what we want for TEE security, and ngrok's policy confirms it.

**2. Start the simulator**

```bash
phala simulator start
```

**3. Run with docker compose**

```bash
export DSTACK_SOCK=~/.phala-cloud/simulator/0.5.3/dstack.sock
export NGROK_AUTHTOKEN=your_token_here
docker compose up
```

Watch the logs for the ngrok URL:
```
ngrok-1  | lvl=info msg="started tunnel" url=tcp://0.tcp.ngrok.io:12345
app-1    | Cert fingerprint: f8f240da59e4b304...
app-1    | HTTPS server on :8443
```

**4. Verify the attestation-bound certificate**

```bash
python3 verify_tls.py https://0.tcp.ngrok.io:12345
```

Output:
```
Verifying: https://0.tcp.ngrok.io:12345

1. Connecting and getting certificate...
   Certificate fingerprint: f8f240da59e4b304...
2. Fetching attestation...
   Attested fingerprint:    f8f240da59e4b304...
3. Verifying certificate matches attestation...
   Certificate fingerprint matches attestation
4. Verifying attestation...
   Quote present (full verification requires trust-center)

============================================================
SUCCESS: TLS certificate is bound to TEE attestation
The connection is end-to-end secure regardless of relay.
```

## How It Works

**docker-compose.yaml** runs two services:
- `app` - HTTPS server with self-signed cert, fingerprint in attestation
- `ngrok` - TCP tunnel that passes through encrypted traffic untouched

**index.mjs** generates the cert and binds it to attestation:
```javascript
// Generate self-signed cert at startup
execSync(`openssl req -x509 -newkey rsa:2048 ... -subj "/CN=tee-oracle"`)

// Hash the certificate (matches what TLS clients see)
const certFingerprint = createHash("sha256").update(certDer).digest("hex")

// Include fingerprint in attestation via report_data
app.get("/attestation", async (req, res) => {
  const quote = await client.getQuote(Buffer.from(certFingerprint, "hex"))
  res.json({ certFingerprint, quote: quote.quote.toString("hex") })
})
```

**verify_tls.py** checks that the TLS cert matches the attestation:
1. Connect and get certificate fingerprint from TLS handshake
2. Fetch `/attestation` endpoint
3. Verify fingerprints match
4. Verify the attestation quote

### Local-Only Testing

Without ngrok (localhost only):
```bash
docker compose run --rm -p 8443:8443 \
  -v ~/.phala-cloud/simulator/0.5.3/dstack.sock:/var/run/dstack.sock app
python3 verify_tls.py https://localhost:8443
```

---

## Approach 2: Let's Encrypt with TLS Passthrough

The TEE generates a keypair and CSR. You handle the ACME DNS-01 challenge externally, then POST the signed cert back. The TEE serves HTTPS directly — the gateway just passes through encrypted traffic.

```
┌────────┐                  ┌─────────────────────┐         ┌─────────────────┐
│ Client │ ─ TLS (LE cert) ─│  dstack-gateway     │─ TCP ─ │ TEE App         │
│        │                  │  (passthrough)      │        │ (HTTPS on 8443) │
└────────┘                  └─────────────────────┘         └─────────────────┘
         Gateway sees encrypted bytes only
```

**Gateway URL patterns:**
- `<id>-8080.<domain>` → HTTP to port 8080 (setup endpoint)
- `<id>-8443s.<domain>` → TLS passthrough to port 8443 (the "s" suffix)

### Deploy and Get CSR

```bash
phala deploy -n tee-le-demo -c docker-compose-letsencrypt.yaml
# Wait for it to start...

# Get the CSR
curl https://<app-id>-8080.dstack-pha-prod5.phala.network/csr > tee.csr
```

### Complete ACME DNS-01 Challenge

Using acme.sh with Cloudflare:
```bash
export CF_Token="your-cloudflare-api-token"

# Submit CSR to Let's Encrypt
docker run --rm -v $(pwd):/acme.sh \
  -e CF_Token="$CF_Token" \
  neilpang/acme.sh \
  --signcsr --csr /acme.sh/tee.csr \
  --dns dns_cf \
  -d oracle.yourdomain.com
```

Or manually:
1. Submit CSR to your ACME client
2. Add the TXT record for `_acme-challenge.oracle.yourdomain.com`
3. Complete the challenge and get the signed cert

### POST Certificate to TEE

```bash
curl -X POST --data-binary @oracle.yourdomain.com.cer \
  https://<app-id>-8080.dstack-pha-prod5.phala.network/cert
```

The TEE starts its HTTPS server with the signed cert.

### Access via TLS Passthrough

```bash
# Via gateway passthrough (note the "s" suffix)
curl https://<app-id>-8443s.dstack-pha-prod5.phala.network/

# Or via your custom domain (after setting CNAME)
curl https://oracle.yourdomain.com/
```

### Attested TLS Verification

The cert fingerprint is bound to the TEE attestation:

```bash
# 1. Get cert fingerprint from TLS connection
echo | openssl s_client -connect <app-id>-8443s.dstack-pha-prod5.phala.network:443 2>/dev/null | \
  openssl x509 -fingerprint -sha256 -noout

# 2. Compare with attestation
curl https://<app-id>-8080.dstack-pha-prod5.phala.network/attestation
```

For full Attested TLS with Certificate Transparency: enumerate all certs issued for your domain via CT logs, verify each fingerprint appears in a valid TEE attestation.

## Other Connectivity Options

| Method | TLS Termination | Notes |
|--------|-----------------|-------|
| ngrok TCP | Your app | Free w/ verification, random port |
| ngrok TCP + CNAME | Your app | Free, custom domain, random port |
| ngrok TLS + domain | Your app | Paid, custom domain, port 443 |
| SSH -R | Your app | Requires server with public IP |
| dstack gateway | Gateway TEE | Trusted relay (TEE-to-TEE) |
| Direct IP | Your app | Production deployments |

## Key Insight

**Attested TLS combines CA trust with code trust.**

- Without attestation: you trust the CA didn't misissue, the DNS wasn't hijacked, the server operator is honest
- With attestation: you trust the verified code that holds the private key

Both approaches have their place:
- Self-signed + attestation is simpler but requires custom verification
- CA + attestation (Attested TLS) works with browsers AND provides additional assurance

The common thread: **bind the certificate to attested code.** Whether the cert is self-signed or CA-signed, the attestation proves which code generated it.

## Exercise: Let's Encrypt Integration

For browser-friendly TLS without certificate warnings, you can use Let's Encrypt with DNS-01 challenge:

1. TEE generates keypair and exposes CSR via `/csr` endpoint
2. External orchestrator fetches CSR, runs ACME DNS-01 challenge
3. Orchestrator posts signed cert back to TEE via `/cert` endpoint
4. TEE starts HTTPS with the LE cert, fingerprint still in attestation

This flow works for real TEE deployments where you can't run commands inside the enclave. The attestation binding still applies - the LE cert fingerprint is included in the quote.

## Exercise: UDP Hole Punching

For direct peer-to-peer connectivity without any relay, UDP hole punching with WireGuard can establish direct connections between TEEs. See [WIP: p2p-wg](https://github.com/amiller/dstack-examples/tree/holepunch/p2p-wg) for an experimental implementation.

## Next Steps

- [05-onchain-authorization](../05-onchain-authorization): On-chain verification
