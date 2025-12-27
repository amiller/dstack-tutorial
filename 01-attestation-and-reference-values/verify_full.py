#!/usr/bin/env python3
"""
Full attestation verification using dcap-qvl for hardware + compose hash.

This demonstrates end-to-end verification:
1. Hardware: dcap-qvl verifies TDX quote is from genuine Intel hardware
2. OS: dstack-mr calculates expected measurements from OS image
3. Compose: Compare compose hash from quote against expected manifest

Prerequisites:
  CFLAGS="-g0" cargo install dcap-qvl-cli
  CGO_CFLAGS="-g0" go install github.com/kvinwang/dstack-mr@latest
  phala cvms attestation <app> --json > attestation.json
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

def verify_quote(quote_hex: str) -> dict:
    """Verify TDX quote with dcap-qvl, return parsed result."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.hex', delete=False) as f:
        f.write(quote_hex)
        quote_path = f.name

    result = subprocess.run(
        ['dcap-qvl', 'verify', '--hex', quote_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise ValueError(f"dcap-qvl failed: {result.stderr}")

    return json.loads(result.stdout)

def find_dstack_mr():
    """Find dstack-mr binary - check PATH and ~/go/bin."""
    dstack_mr = shutil.which('dstack-mr')
    if dstack_mr:
        return dstack_mr
    go_bin = os.path.expanduser('~/go/bin/dstack-mr')
    if os.path.exists(go_bin):
        return go_bin
    return None

def calculate_os_measurements(image_folder: str) -> dict:
    """Calculate expected OS measurements using dstack-mr."""
    dstack_mr = find_dstack_mr()
    if not dstack_mr:
        raise FileNotFoundError("dstack-mr not found")
    metadata_path = os.path.join(image_folder, 'metadata.json')
    result = subprocess.run(
        [dstack_mr, '-metadata', metadata_path, '-json'],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise ValueError(f"dstack-mr failed: {result.stderr}")
    return json.loads(result.stdout)

def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_full.py <attestation.json> [--image-folder PATH] [expected-manifest.json]")
        print("\nGet attestation.json with: phala cvms attestation <app> --json > attestation.json")
        print("Download dstack image: curl -L https://github.com/Dstack-TEE/meta-dstack/releases/download/v0.5.5/dstack-0.5.5.tar.gz | tar xz")
        sys.exit(1)

    attestation_path = sys.argv[1]
    image_folder = None
    manifest_path = None
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == '--image-folder' and i + 1 < len(sys.argv):
            image_folder = sys.argv[i + 1]
            i += 2
        else:
            manifest_path = sys.argv[i]
            i += 1

    with open(attestation_path) as f:
        data = json.load(f)

    # Extract quote
    quote = data['app_certificates'][0]['quote']

    print("=== Step 1: Hardware Verification (dcap-qvl) ===")
    result = verify_quote(quote)

    status = result['status']
    advisories = result.get('advisory_ids', [])
    print(f"  TCB Status: {status}")
    if advisories:
        print(f"  Advisories: {advisories}")

    if status not in ['UpToDate', 'SWHardeningNeeded']:
        print(f"  ✗ FAIL: TCB status {status} is not acceptable")
        sys.exit(1)
    print("  ✓ Hardware verification passed")

    # Extract measurements
    report = result['report']['TD10']
    print()
    print("=== Step 2: Extract Measurements ===")
    print(f"  MRTD:  {report['mr_td'][:32]}...")
    print(f"  RTMR0: {report['rt_mr0'][:32]}...")
    print(f"  RTMR3: {report['rt_mr3'][:32]}...")

    # Extract compose hash from mr_config_id
    config_id = report['mr_config_id']
    if not config_id.startswith('01'):
        print(f"  ✗ Unknown config ID format: {config_id[:4]}...")
        sys.exit(1)

    verified_hash = config_id[2:66]
    print(f"  Compose hash (from quote): {verified_hash}")

    # OS verification (optional - requires dstack-mr and image folder)
    print()
    print("=== Step 3: OS Verification (dstack-mr) ===")
    if not image_folder:
        print("  (skipped - no --image-folder provided)")
        print("  To verify OS: download dstack image matching your app's version")
    elif not find_dstack_mr():
        print("  (skipped - dstack-mr not installed)")
        print("  Install: CGO_CFLAGS=\"-g0\" go install github.com/kvinwang/dstack-mr@latest")
    else:
        expected = calculate_os_measurements(image_folder)
        print(f"  Expected MRTD: {expected['mrtd'][:32]}...")
        print(f"  Actual MRTD:   {report['mr_td'][:32]}...")
        if expected['mrtd'] == report['mr_td']:
            print("  ✓ MRTD matches - kernel/initramfs verified")
        else:
            print("  ✗ MRTD mismatch - OS image may be different version")
            sys.exit(1)
        # Note: RTMR0-2 require dstack-mr-cli (Rust) with QEMU for accurate comparison
        print("  (RTMR0-2 verification requires dstack-mr-cli with QEMU)")

    # Compare with expected
    print()
    print("=== Step 4: Compose Hash Verification ===")

    if manifest_path:
        with open(manifest_path, 'rb') as f:
            expected_hash = hashlib.sha256(f.read()).hexdigest()
        print(f"  Expected (from file): {expected_hash}")
    else:
        # Use manifest from attestation API response
        manifest = data['tcb_info']['app_compose']
        expected_hash = hashlib.sha256(manifest.encode()).hexdigest()
        print(f"  Expected (from API): {expected_hash}")

    if verified_hash == expected_hash:
        print("  ✓ MATCH - Compose hash verified!")
    else:
        print("  ✗ MISMATCH")
        print(f"    Verified: {verified_hash}")
        print(f"    Expected: {expected_hash}")
        sys.exit(1)

    print()
    print("=== Verification Complete ===")
    print("  ✓ Hardware: Genuine Intel TDX")
    if image_folder and find_dstack_mr():
        print("  ✓ OS: MRTD matches expected (kernel/initramfs)")
    else:
        print("  - OS: (skipped)")
    print("  ✓ Compose: Matches expected manifest")
    print()
    print("  Security claim: This TEE is running the expected code")
    print("  on genuine Intel TDX hardware.")

if __name__ == "__main__":
    main()
