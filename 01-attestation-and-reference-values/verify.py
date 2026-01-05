#!/usr/bin/env python3
"""
Verify a public dstack app using only public endpoints.

This demonstrates auditor-accessible verification:
1. Fetch attestation (quote, eventlog) from Phala Cloud API
2. Fetch app_compose from the app's 8090 endpoint
3. Compute compose hash and compare with mr_config_id
4. Optionally verify hardware with dcap-qvl

Usage:
  python3 verify_public_app.py <app_id>
  python3 verify_public_app.py c951a6fa03ebc23bc469916476a51977219bc2a2

Prerequisites:
  CFLAGS="-g0" cargo install dcap-qvl-cli  # optional, for hardware verification
"""
import hashlib
import html
import json
import re
import subprocess
import sys
import tempfile
import urllib.request

def fetch_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'dstack-tutorial/1.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def fetch_html(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'dstack-tutorial/1.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode('utf-8')

def extract_app_compose_from_html(html_content):
    """Extract app_compose JSON from tappd info page."""
    content = html.unescape(html_content)
    match = re.search(r'"app_compose":\s*"((?:[^"\\]|\\.)*)"', content, re.DOTALL)
    if not match:
        return None
    escaped = match.group(1)
    compose_json = json.loads('"' + escaped + '"')
    return json.loads(compose_json)

def compute_compose_hash(compose_obj):
    """Compute compose hash matching dstack's canonical JSON."""
    canonical = json.dumps(compose_obj, separators=(',', ':'), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()

def verify_quote_hardware(quote_hex):
    """Verify TDX quote with dcap-qvl (optional)."""
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.hex', delete=False) as f:
            # Remove 0x prefix if present
            if quote_hex.startswith('0x'):
                quote_hex = quote_hex[2:]
            f.write(quote_hex)
            quote_path = f.name
        result = subprocess.run(
            ['dcap-qvl', 'verify', '--hex', quote_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return None, f"dcap-qvl failed: {result.stderr}"
        return json.loads(result.stdout), None
    except FileNotFoundError:
        return None, "dcap-qvl not installed (optional)"

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 verify_public_app.py <app_id>")
        print("\nExample:")
        print("  python3 verify_public_app.py c951a6fa03ebc23bc469916476a51977219bc2a2")
        sys.exit(1)

    app_id = sys.argv[1]
    print(f"=== Verifying Public App: {app_id} ===\n")

    # Step 1: Fetch attestation from Phala Cloud API
    print("Step 1: Fetching attestation from Phala Cloud API...")
    try:
        attestation = fetch_json(f"https://cloud-api.phala.network/api/v1/apps/{app_id}/attestations")
        print(f"  ✓ Found {len(attestation.get('instances', []))} instance(s)")
        print(f"  KMS version: {attestation.get('kms_info', {}).get('version', 'unknown')}")

        if not attestation.get('instances'):
            print("  ✗ No running instances")
            sys.exit(1)

        instance = attestation['instances'][0]
        quote = instance.get('quote', '')
        image_version = instance.get('image_version', 'unknown')
        print(f"  Image: {image_version}")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        sys.exit(1)

    # Step 2: Fetch app_compose from 8090 endpoint
    print("\nStep 2: Fetching app_compose from app endpoint...")
    # Determine gateway domain from attestation
    gateway_domain = "dstack-base-prod7.phala.network"  # default, could be extracted
    info_url = f"https://{app_id}-8090.{gateway_domain}/"

    try:
        html_content = fetch_html(info_url)
        compose = extract_app_compose_from_html(html_content)
        if not compose:
            print(f"  ✗ Could not extract app_compose from {info_url}")
            sys.exit(1)
        print(f"  ✓ App name: {compose.get('name', 'unknown')}")
        print(f"  Manifest version: {compose.get('manifest_version')}")
        print(f"  KMS enabled: {compose.get('kms_enabled')}")
        print(f"  Allowed envs: {compose.get('allowed_envs', [])}")
    except Exception as e:
        print(f"  ✗ Failed to fetch from {info_url}: {e}")
        sys.exit(1)

    # Step 3: Compute and compare compose hash
    print("\nStep 3: Verifying compose hash...")
    computed_hash = compute_compose_hash(compose)
    print(f"  Computed hash: {computed_hash}")

    # Step 4: Hardware verification (optional)
    print("\nStep 4: Hardware verification (dcap-qvl)...")
    hw_result, hw_error = verify_quote_hardware(quote)
    if hw_result:
        status = hw_result.get('status', 'unknown')
        print(f"  ✓ TCB Status: {status}")

        # Extract mr_config_id from quote
        report = hw_result.get('report', {}).get('TD10', {})
        config_id = report.get('mr_config_id', '')
        if config_id.startswith('01'):
            quote_hash = config_id[2:66]
            print(f"  Compose hash from quote: {quote_hash}")

            if quote_hash == computed_hash:
                print("  ✓ MATCH - Compose hash verified!")
            else:
                print("  ✗ MISMATCH")
                print(f"    Quote:    {quote_hash}")
                print(f"    Computed: {computed_hash}")
        else:
            print(f"  Unknown config_id format: {config_id[:10]}...")
    else:
        print(f"  (skipped: {hw_error})")

    # Summary
    print("\n=== Audit Summary ===")
    print(f"App ID: {app_id}")
    print(f"Contract: 0x{app_id}")
    print(f"Image: {image_version}")
    print()
    print("Docker images in compose:")
    dc = compose.get('docker_compose_file', '')
    for line in dc.split('\n'):
        if 'image:' in line:
            print(f"  {line.strip()}")
    print()
    print("To fully audit this app:")
    print("  1. Review the docker-compose.yaml above")
    print("  2. Check if images are from trusted sources")
    print("  3. Note allowed_envs - these can change behavior at runtime")
    print("  4. Check pre_launch_script if present")

if __name__ == "__main__":
    main()
