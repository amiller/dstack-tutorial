import { DstackClient } from "@phala/dstack-sdk"
import { createServer } from "http"
import https from "https"
import crypto from "crypto"

const client = new DstackClient()
const API_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"

function fetchWithTls(url) {
  return new Promise((resolve, reject) => {
    https.get(url, res => {
      const cert = res.socket.getPeerCertificate()
      let body = ""
      res.on("data", c => body += c)
      res.on("end", () => resolve({
        data: JSON.parse(body),
        tlsFingerprint: cert.fingerprint256,
        tlsIssuer: cert.issuer?.O,
        tlsValidTo: cert.valid_to
      }))
    }).on("error", reject)
  })
}

async function getAttestedPrice() {
  const { data, tlsFingerprint, tlsIssuer, tlsValidTo } = await fetchWithTls(API_URL)
  const statement = {
    source: "api.coingecko.com",
    price: data.bitcoin.usd,
    tlsFingerprint,
    tlsIssuer,
    tlsValidTo,
    timestamp: Date.now()
  }
  const hash = crypto.createHash("sha256").update(JSON.stringify(statement)).digest("hex")
  const quote = await client.getQuote(hash)
  return { statement, reportDataHash: hash, quote: quote.quote }
}

createServer(async (req, res) => {
  res.writeHead(200, { "Content-Type": "application/json" })
  if (req.url === "/price") {
    res.end(JSON.stringify(await getAttestedPrice(), null, 2))
  } else {
    const info = await client.info()
    res.end(JSON.stringify({ endpoints: ["/", "/price"], appId: info.app_id }, null, 2))
  }
}).listen(8080, () => console.log("Oracle at http://localhost:8080"))
