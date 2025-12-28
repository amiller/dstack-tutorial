import { DstackClient } from "@phala/dstack-sdk"
import express from "express"
import { createServer } from "https"
import { execSync } from "child_process"
import { readFileSync, writeFileSync, existsSync } from "fs"
import { createHash } from "crypto"

const client = new DstackClient()
const app = express()
app.use(express.text({ type: "*/*" }))

// Generate keypair and CSR at startup
if (!existsSync("/tmp/key.pem")) {
  console.log("Generating keypair and CSR...")
  execSync(`openssl genrsa -out /tmp/key.pem 2048`)
  execSync(`openssl req -new -key /tmp/key.pem -out /tmp/csr.pem -subj "/CN=tee-oracle"`)
}

const csr = readFileSync("/tmp/csr.pem", "utf8")
const key = readFileSync("/tmp/key.pem")
let httpsServer = null

app.get("/", (req, res) => {
  const hasCert = existsSync("/tmp/cert.pem")
  res.json({
    status: hasCert ? "ready" : "waiting_for_cert",
    message: hasCert
      ? "HTTPS server running. Access via <id>-8443s.<domain> for TLS passthrough."
      : "Waiting for certificate. GET /csr, complete ACME challenge, POST cert to /cert",
    endpoints: ["/csr", "/cert", "/attestation"]
  })
})

app.get("/csr", (req, res) => {
  res.type("application/x-pem-file").send(csr)
})

app.post("/cert", (req, res) => {
  if (httpsServer) {
    return res.status(400).json({ error: "HTTPS server already running" })
  }

  const certPem = req.body
  if (!certPem.includes("BEGIN CERTIFICATE")) {
    return res.status(400).json({ error: "Invalid certificate PEM" })
  }

  writeFileSync("/tmp/cert.pem", certPem)
  console.log("Certificate received, starting HTTPS server...")

  // Start HTTPS server
  startHttpsServer()
  res.json({ status: "ok", message: "HTTPS server started on :8443" })
})

app.get("/attestation", async (req, res) => {
  const info = await client.getInfo()

  let certFingerprint = null
  if (existsSync("/tmp/cert.pem")) {
    const certPem = readFileSync("/tmp/cert.pem")
    const certDer = Buffer.from(
      certPem.toString().replace(/-----BEGIN CERTIFICATE-----/, '')
        .replace(/-----END CERTIFICATE-----/, '')
        .replace(/\n/g, ''),
      'base64'
    )
    certFingerprint = createHash("sha256").update(certDer).digest("hex")
  }

  const reportData = certFingerprint
    ? Buffer.from(certFingerprint, "hex")
    : Buffer.alloc(64)
  const quote = await client.getQuote(reportData)

  res.json({
    appId: info.app_id,
    certFingerprint,
    quote: Buffer.from(quote.quote).toString("hex").slice(0, 200) + "..."
  })
})

function startHttpsServer() {
  const cert = readFileSync("/tmp/cert.pem")
  httpsServer = createServer({ cert, key }, (req, res) => {
    res.setHeader("Content-Type", "application/json")

    if (req.url === "/") {
      res.end(JSON.stringify({ status: "ok", tls: true }))
    } else if (req.url === "/attestation") {
      client.getInfo().then(info => {
        const certDer = Buffer.from(
          cert.toString().replace(/-----BEGIN CERTIFICATE-----/, '')
            .replace(/-----END CERTIFICATE-----/, '')
            .replace(/\n/g, ''),
          'base64'
        )
        const fingerprint = createHash("sha256").update(certDer).digest("hex")
        client.getQuote(Buffer.from(fingerprint, "hex")).then(quote => {
          res.end(JSON.stringify({
            appId: info.app_id,
            certFingerprint: fingerprint,
            quote: Buffer.from(quote.quote).toString("hex").slice(0, 200) + "..."
          }))
        })
      })
    } else {
      res.statusCode = 404
      res.end(JSON.stringify({ error: "not found" }))
    }
  })

  httpsServer.listen(8443, () => {
    console.log("HTTPS server on :8443 (access via <id>-8443s.<domain>)")
  })
}

// Start HTTP server for setup
app.listen(8080, () => {
  console.log("HTTP setup server on :8080")
  console.log("1. GET /csr to get the CSR")
  console.log("2. Complete ACME DNS-01 challenge externally")
  console.log("3. POST signed cert to /cert")
  console.log("4. Access HTTPS via <id>-8443s.<domain>")
})
