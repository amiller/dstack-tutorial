import { DstackClient } from "@phala/dstack-sdk"
import { createServer } from "https"
import { execSync } from "child_process"
import { readFileSync, existsSync } from "fs"
import { createHash } from "crypto"

const client = new DstackClient()

// Generate self-signed cert if not exists
if (!existsSync("/tmp/cert.pem")) {
  execSync(`openssl req -x509 -newkey rsa:2048 -keyout /tmp/key.pem -out /tmp/cert.pem -days 365 -nodes -subj "/CN=tee-oracle"`)
}

const certPem = readFileSync("/tmp/cert.pem")
const key = readFileSync("/tmp/key.pem")

// Extract DER from PEM and hash it (matches what TLS clients see)
const certDer = Buffer.from(
  certPem.toString().replace(/-----BEGIN CERTIFICATE-----/, '')
    .replace(/-----END CERTIFICATE-----/, '')
    .replace(/\n/g, ''),
  'base64'
)
const certFingerprint = createHash("sha256").update(certDer).digest("hex")

console.log("Cert fingerprint:", certFingerprint)

async function handleRequest(req, res) {
  res.setHeader("Content-Type", "application/json")

  if (req.url === "/attestation") {
    // Pass cert fingerprint as report_data (hex string -> buffer -> first 64 bytes)
    const reportData = Buffer.from(certFingerprint, "hex")
    const quote = await client.getQuote(reportData)
    res.end(JSON.stringify({
      certFingerprint,
      quote: Buffer.from(quote.quote).toString("hex"),
      eventLog: quote.event_log
    }))
    return
  }

  if (req.url === "/") {
    res.end(JSON.stringify({
      status: "ok",
      certFingerprint,
      message: "Fetch /attestation to verify this certificate"
    }))
    return
  }

  res.statusCode = 404
  res.end(JSON.stringify({ error: "not found" }))
}

const server = createServer({ cert: certPem, key }, handleRequest)
server.listen(8443, () => console.log("HTTPS server on :8443"))
