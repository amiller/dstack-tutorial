# Tutorial 04: Gateways and TLS

How to expose TEE applications over HTTPS while preserving verifiable trust.

## Prerequisites

Complete [01-attestation-and-reference-values](../01-attestation-and-reference-values) first.

## The Core Insight

**Attestation binds a certificate to verified code.**

Whether the cert is self-signed or CA-signed, whether it's in your app or a gateway, the same principle applies: you can verify that the private key was generated inside attested TEE code.

This tutorial explores different approaches to TLS with TEEs:

| Approach | Certificate | TLS Termination | Verification |
|----------|-------------|-----------------|--------------|
| Self-signed + attestation | Self-signed | Your app | Client MUST check attestation |
| Gateway (default) | CA-signed | Gateway TEE | Browser trusts CA; client CAN check gateway attestation |
| Gateway (passthrough) | CA-signed | Your app | Browser trusts CA; client CAN check app attestation |

All three approaches can be verified via attestation. The difference is where TLS terminates and whether browsers work without warnings.

---

## The dstack Gateway

The dstack gateway is a TEE-based reverse proxy. When you deploy to Phala Cloud, your app gets URLs like:
- `<app-id>-<port>.dstack-pha-prod9.phala.network` — HTTP to port (gateway terminates TLS)
- `<app-id>-<port>s.dstack-pha-prod9.phala.network` — TLS passthrough (the "s" suffix)

### Gateway as Attestable TEE

The gateway itself runs in a TEE. You can verify it:

```bash
# List nodes to see gateway info
phala nodes list

# Example output shows Gateway App ID (on-chain attestation):
#   Gateway App ID: 0x55760b065A3f1EAbdb1a4d7AbB94950f31B91A84
```

When the gateway terminates TLS (default mode, no "s" suffix), traffic flow is:
```
Client → TLS → Gateway TEE (decrypts, sees plaintext) → HTTP → App TEE
```

The gateway is trusted because it's attested. You can start auditing via its on-chain AppAuth contract:
- [Gateway AppAuth on Base](https://basescan.org/address/0x55760b065A3f1EAbdb1a4d7AbB94950f31B91A84#events) — shows registered compose hashes

(Full gateway audit trail TBD — getting attestations for those compose hashes is an open thread.)

### Gateway in Passthrough Mode

With the "s" suffix, the gateway passes encrypted bytes through:
```
Client → TLS → Gateway TEE (passes encrypted) → TLS → App TEE (decrypts)
```

Now the gateway only sees encrypted traffic. Same trust model as any TCP relay.

### Simulator Limitation

The local dstack simulator doesn't include a gateway. For local development, you need an alternative relay (ngrok, stunnel, SSH tunnel). This tutorial covers these alternatives—and in doing so, demonstrates that **any TCP relay works when TLS terminates in the TEE**.

---

## Approach 1: Attested TLS (Self-Signed + Attestation)

The purest form: TEE generates a self-signed cert at startup, fingerprint goes in attestation. Clients verify the TLS cert matches what's attested. No CA trust required.

```
┌────────┐         ┌─────────────┐         ┌─────────────────────────┐
│ Client │ ─ TLS ─ │   Relay     │ ─ TCP ─ │ TEE                     │
│        │         │(ngrok/SSH/  │         │ ┌─────────────────────┐ │
│        │         │ stunnel/    │         │ │ Self-signed cert    │ │
│        │         │ gateway-s/  │         │ │ Fingerprint in      │ │
│        │         │ ...)        │         │ │ attestation         │ │
└────────┘         └─────────────┘         └─────────────────────────┘
          Relay only sees encrypted bytes
```

### Why Any Relay Works

When TLS terminates in the TEE, the relay:
- Cannot read plaintext
- Cannot modify requests/responses
- Cannot forge the TEE's identity

The relay operator sees encrypted bytes and connection metadata. The cryptographic properties are unaffected.

| Relay | Command | Notes |
|-------|---------|-------|
| ngrok | `ngrok tcp <port>` | Free (w/ verification), random port |
| stunnel | `stunnel -c -d 8443 -r <tee>:443` | Decrypts locally |
| socat | `socat TCP-LISTEN:8443,fork OPENSSL:<tee>:443` | Unix, simple |
| SSH | `ssh -R 8443:localhost:443 server` | Requires server with public IP |
| Gateway (passthrough) | `<app-id>-<port>s.<gateway>` | The "s" suffix |

### Running with ngrok

**1. Start the simulator**
```bash
phala simulator start
```

**2. Run with docker compose**
```bash
export DSTACK_SOCK=~/.phala-cloud/simulator/0.5.3/dstack.sock
export NGROK_AUTHTOKEN=your_token_here
docker compose up
```

Watch for the ngrok URL:
```
ngrok-1  | lvl=info msg="started tunnel" url=tcp://0.tcp.ngrok.io:12345
app-1    | Cert fingerprint: f8f240da59e4b304...
```

**3. Verify the attestation-bound certificate**
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

SUCCESS: TLS certificate is bound to TEE attestation
The connection is end-to-end secure regardless of relay.
```

### Other TCP Relay Examples

**stunnel** (decrypts locally):
```bash
stunnel -c -d 127.0.0.1:8080 -r <app-id>-443s.dstack-pha-prod9.phala.network:443
```

**socat** (TCP passthrough):
```bash
socat TCP-LISTEN:8443,fork,reuseaddr \
  OPENSSL:<app-id>-443s.dstack-pha-prod9.phala.network:443
```

**SSH reverse tunnel**:
```bash
ssh -R 8443:localhost:443 user@your-server.com
```

### Local-Only Testing
```bash
docker compose run --rm -p 8443:8443 \
  -v ~/.phala-cloud/simulator/0.5.3/dstack.sock:/var/run/dstack.sock app
python3 verify_tls.py https://localhost:8443
```

---

## Approach 2: CA Certificate + Attestation

For browser compatibility, use a CA-signed certificate. The TEE is still attestable—the CA cert just means browsers work without warnings.

Two sub-approaches:
1. **Gateway terminates TLS** — Gateway has CA cert, gateway is attested
2. **Gateway passthrough** — Your app has CA cert, your app is attested

Both provide CA trust (browsers work) AND attestation (code is verifiable).

### Gateway TLS Termination (Default)

When you access `<app-id>-8080.dstack-pha-prod9.phala.network`, the gateway:
- Terminates TLS using the gateway's wildcard cert
- Proxies plaintext HTTP to your app

The gateway sees plaintext, but the gateway is a TEE. You can verify its attestation:
```bash
# Gateway App ID from `phala nodes list`
# 0x55760b065A3f1EAbdb1a4d7AbB94950f31B91A84
```

### Gateway Passthrough with Custom Domain

For your app to handle TLS directly (with a CA cert), use passthrough mode with a custom domain:

```
┌────────┐                  ┌─────────────────────┐         ┌─────────────────┐
│ Client │ ─ TLS (LE cert) ─│  dstack gateway     │─ TCP ─ │ TEE App         │
│        │                  │  (passthrough)      │        │ (HTTPS on 443)  │
└────────┘                  └─────────────────────┘         └─────────────────┘
         Gateway sees encrypted bytes only
```

**How gateway routing works:**

The gateway routes based on SNI (Server Name Indication):
- `<app-id>-<port>.<gateway>` → HTTP to port
- `<app-id>-<port>s.<gateway>` → TLS passthrough
- Custom domain → TXT lookup at `_dstack-app-address.<domain>` → passthrough

**Gateway compatibility:**

| Gateway | TXT Routing | Notes |
|---------|-------------|-------|
| prod9   | ✅ Yes      | `_.dstack-pha-prod9.phala.network` |
| prod5   | ❌ No       | Only direct URL patterns |
| prod7   | ❌ No       | Only direct URL patterns |

### Manual Let's Encrypt Setup

**1. Deploy to prod9:**
```bash
DOMAIN=oracle.yourdomain.com phala deploy --node-id 18 \
  -n tee-le-demo -c docker-compose-letsencrypt.yaml -e DOMAIN=oracle.yourdomain.com
```

**2. Get CSR from TEE:**
```bash
curl https://<app-id>-8080.dstack-pha-prod9.phala.network/csr > tee.csr
```

**3. Set DNS records:**
```
CNAME  oracle.yourdomain.com                      → _.dstack-pha-prod9.phala.network
TXT    _dstack-app-address.oracle.yourdomain.com  → <app-id>:443
```

**4. Complete ACME DNS-01 challenge:**
```bash
certbot certonly --manual --preferred-challenges dns \
  -d oracle.yourdomain.com --csr tee.csr
```

**5. POST certificate to TEE:**
```bash
curl -X POST --data-binary @0000_chain.pem \
  https://<app-id>-8080.dstack-pha-prod9.phala.network/cert
```

**6. Access via custom domain:**
```bash
curl https://oracle.yourdomain.com/
# {"status":"ok","tls":true}
```

### dstack-ingress (Automated)

dstack-ingress automates DNS + ACME using a Cloudflare API token:

```yaml
services:
  dstack-ingress:
    image: dstacktee/dstack-ingress:20250929@sha256:2b47b3e538...
    environment:
      - DNS_PROVIDER=cloudflare
      - CLOUDFLARE_API_TOKEN=${CLOUDFLARE_API_TOKEN}
      - DOMAIN=${DOMAIN}
      - GATEWAY_DOMAIN=_.dstack-pha-prod9.phala.network
      - CERTBOT_EMAIL=${CERTBOT_EMAIL}
      - TARGET_ENDPOINT=http://app:80
```

Deploy:
```bash
phala deploy --node-id 18 -c docker-compose-dstack-ingress.yaml -e .env
```

**Note:** The DNS management (CNAME, TXT, CAA records) doesn't need to be in a TEE for the trust model. What matters is:
1. Key generation happens in TEE
2. TLS termination happens in TEE
3. Attestation binds the cert to TEE code

---

## Verification

### App Attestation (8090 endpoint)

Every dstack app exposes attestation info at port 8090:
```bash
curl https://<app-id>-8090.dstack-pha-prod9.phala.network/
```

Returns TCB info: RTMRs, compose hash, event log, device ID.

### Certificate Fingerprint Matching

```bash
# Get cert fingerprint from TLS connection
echo | openssl s_client -connect oracle.yourdomain.com:443 2>/dev/null | \
  openssl x509 -fingerprint -sha256 -noout

# Compare with attestation
curl https://<app-id>-8080.dstack-pha-prod9.phala.network/attestation
```

---

## Summary: What Must Be in TEE?

| Component | Must be in TEE? | Why |
|-----------|-----------------|-----|
| Private key generation | ✅ Yes | Key must never exist outside TEE |
| TLS termination | ✅ Yes | Decryption must happen in TEE |
| Attestation binding | ✅ Yes | Binds cert fingerprint to code |
| TCP relay (ngrok, gateway, SSH) | ❌ No | Only sees encrypted bytes |
| DNS management | ❌ No | Domain ownership ≠ code identity |
| ACME challenge | ❌ No | Proves domain ownership only |

The trust model: **attestation proves which code holds the private key.** Relays, DNS, and CAs are infrastructure that doesn't affect this.

---

## Exercises

### Exercise 1: Match certificate to attestation

For a deployed app with a custom domain, get the cert fingerprint:
```bash
echo | openssl s_client -connect <domain>:443 2>/dev/null | openssl x509 -fingerprint -sha256 -noout
```

Then fetch the app's attestation and find the same fingerprint. This proves the TLS key is held by attested code.

---

## TODO: Certificate Transparency Verification

For domains using CT, you can provide strong assurance that all certificates were issued by attested TEE code:

1. Enumerate all certs for a domain via CT logs (e.g., crt.sh)
2. For each cert fingerprint, verify it appears in a valid TEE attestation
3. If all fingerprints are attested, no rogue certs exist undetected

---

## Next Steps

- [05-onchain-authorization](../05-onchain-authorization): On-chain verification
