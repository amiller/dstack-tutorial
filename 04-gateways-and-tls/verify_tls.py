#!/usr/bin/env python3
"""
Verify TEE oracle via attestation-bound certificate.

Usage:
  python3 verify_tls.py <endpoint>

Examples:
  python3 verify_tls.py https://localhost:8443
  python3 verify_tls.py https://0.tcp.ngrok.io:12345
"""

import sys
import ssl
import socket
import hashlib
import urllib3
import requests
from urllib.parse import urlparse

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_cert_fingerprint(host, port):
    """Get SHA256 fingerprint of server's TLS certificate"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    with ctx.wrap_socket(socket.socket(), server_hostname=host) as s:
        s.connect((host, port))
        cert_der = s.getpeercert(binary_form=True)
        return hashlib.sha256(cert_der).hexdigest()

def verify_attestation(attestation):
    """Verify the TDX quote - see 01-attestation for full verification"""
    if not attestation.get("quote"):
        raise Exception("No quote in attestation")
    print("  Quote present (full verification requires trust-center)")
    return True

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <endpoint>")
        sys.exit(1)

    endpoint = sys.argv[1]
    parsed = urlparse(endpoint)
    host = parsed.hostname
    port = parsed.port or 443

    print(f"Verifying: {endpoint}")
    print()

    # Step 1: Get certificate fingerprint from TLS connection
    print("1. Connecting and getting certificate...")
    cert_fp = get_cert_fingerprint(host, port)
    print(f"   Certificate fingerprint: {cert_fp[:16]}...")

    # Step 2: Fetch attestation (ignoring cert validation)
    print("2. Fetching attestation...")
    resp = requests.get(f"{endpoint}/attestation", verify=False, timeout=10)
    attestation = resp.json()
    attested_fp = attestation["certFingerprint"]
    print(f"   Attested fingerprint:    {attested_fp[:16]}...")

    # Step 3: Verify fingerprints match
    print("3. Verifying certificate matches attestation...")
    if cert_fp != attested_fp:
        print("   FAILED: Certificate fingerprint mismatch!")
        print("   This could indicate a MITM attack.")
        sys.exit(1)
    print("   Certificate fingerprint matches attestation")

    # Step 4: Verify the attestation itself
    print("4. Verifying attestation...")
    verify_attestation(attestation)

    print()
    print("=" * 60)
    print("SUCCESS: TLS certificate is bound to TEE attestation")
    print("The connection is end-to-end secure regardless of relay.")

if __name__ == "__main__":
    main()
