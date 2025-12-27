# Tutorial 04: Gateways and TLS

Self-signed TLS with attestation-bound certificates, exposed via ngrok TCP tunnel.

## Prerequisites

Complete [01-attestation-and-reference-values](../01-attestation-and-reference-values) first.

## The Problem

TEE apps need TLS, but:
- Let's Encrypt requires DNS control
- HTTP relay services terminate TLS and see plaintext
- Trusting a CA or relay breaks end-to-end TEE integrity

## The Solution: Attestation-Bound Certificates

The TEE generates a self-signed certificate. The certificate fingerprint is included in the attestation. Clients verify the TLS cert matches what's attested - no CA needed.

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

## Running with ngrok

### 1. Get ngrok auth token

Sign up at [ngrok.com](https://ngrok.com) (free). TCP tunnels require identity verification (credit card on file, not charged).

*Why does ngrok require verification for TCP?* Because they can't inspect the traffic - it's encrypted end-to-end. This is exactly what we want for TEE security, and ngrok's policy confirms it.

### 2. Start the simulator

```bash
phala simulator start
```

### 3. Run with docker compose

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

### 4. Verify the attestation-bound certificate

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

## Local-Only Testing

Without ngrok (localhost only):
```bash
docker compose run --rm -p 8443:8443 \
  -v ~/.phala-cloud/simulator/0.5.3/dstack.sock:/var/run/dstack.sock app
python3 verify_tls.py https://localhost:8443
```

## Custom Domain with ngrok (Optional)

You can use your own domain with the free TCP tunnel:

1. Add a CNAME: `tee.yourdomain.com → 0.tcp.ngrok.io`
2. Run the tunnel, note the port from logs (e.g., `:12345`)
3. Access via `https://tee.yourdomain.com:12345`

The port is ephemeral, but the attestation-bound certificate still works - clients verify the cert fingerprint matches the attestation regardless of hostname.

For stable ports, ngrok paid plans offer reserved TCP addresses. For port 443 with custom domains, use `ngrok tls --url=yourdomain.com` (TLS passthrough mode, paid).

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

**The certificate doesn't need CA signing.** The attestation IS the trust anchor. By binding the certificate fingerprint to a valid TEE attestation, we prove the certificate was generated inside the TEE. This works through any untrusted relay.

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
