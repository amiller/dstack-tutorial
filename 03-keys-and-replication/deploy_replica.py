#!/usr/bin/env python3
"""
Deploy a CVM replica using existing appId via direct API calls.
This bypasses the CLI's limitation of always deploying a new AppAuth contract.
"""

import os
import json
import platform
import hashlib
import requests
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

CLOUD_API = "https://cloud-api.phala.network/api/v1"

def get_machine_key():
    """Generate machine-specific key like the CLI does"""
    import subprocess
    hostname = platform.node()
    plat = platform.system().lower()
    # Node.js os.arch() returns 'x64' not 'x86_64'
    arch = platform.machine()
    if arch == "x86_64":
        arch = "x64"
    try:
        cpu_model = subprocess.check_output("cat /proc/cpuinfo | grep 'model name' | head -1 | cut -d: -f2", shell=True).decode().strip()
    except:
        cpu_model = ""
    username = os.environ.get("USER", "")

    parts = f"{hostname}|{plat}|{arch}|{cpu_model}|{username}"
    return hashlib.sha256(parts.encode()).digest()

def decrypt_api_key():
    """Decrypt the stored API key"""
    key_file = Path.home() / ".phala-cloud" / "api-key"
    if not key_file.exists():
        return None

    encrypted = key_file.read_text().strip()
    parts = encrypted.split(":")
    if len(parts) != 2:
        return None

    iv = bytes.fromhex(parts[0])
    ciphertext = bytes.fromhex(parts[1])
    key = get_machine_key()[:32]

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()

    # Remove PKCS7 padding
    pad_len = padded[-1]
    return padded[:-pad_len].decode()

API_KEY = os.environ.get("PHALA_CLOUD_API_KEY") or decrypt_api_key()

# First CVM's info - UPDATE THIS with your appId from the first deployment
EXISTING_APP_ID = "c96d55b03ede924c89154348be9dcffd52304af0"
EXISTING_APP_AUTH_ADDRESS = "0x" + EXISTING_APP_ID  # For on-chain KMS, appId IS the contract address

# Target node for replica
TARGET_NODE_ID = 18  # prod9

# Replica name - change this for each replica
REPLICA_NAME = "tee-oracle-option2-replica"

def get_headers():
    return {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }

def read_compose_file():
    with open("docker-compose.yaml", "r") as f:
        return f.read()

def provision_cvm(name: str, compose_content: str, node_id: int, kms_id: str):
    """Step 1: Provision CVM resources"""
    payload = {
        "name": name,
        "image": "dstack-0.5.4",
        "vcpu": 1,
        "memory": 2048,
        "disk_size": 20,
        "teepod_id": node_id,
        "kms_id": kms_id,
        "compose_file": {
            "docker_compose_file": compose_content,
            "allowed_envs": [],
            "features": ["kms"],
            "kms_enabled": True,
            "manifest_version": 2,
            "name": name,
            "public_logs": True,
            "public_sysinfo": True,
            "tproxy_enabled": False
        },
        "env_keys": [],
        "listed": True,
        "instance_type": "tdx.small"
    }

    resp = requests.post(f"{CLOUD_API}/cvms/provision", headers=get_headers(), json=payload)
    resp.raise_for_status()
    return resp.json()

def create_cvm_with_existing_app(app_id: str, compose_hash: str, app_auth_address: str, deployer_address: str):
    """Step 2: Create CVM using existing appId (skip contract deployment)"""
    payload = {
        "app_id": app_id,
        "compose_hash": compose_hash,
        "encrypted_env": "",
        "app_auth_contract_address": app_auth_address,
        "deployer_address": deployer_address
    }

    resp = requests.post(f"{CLOUD_API}/cvms", headers=get_headers(), json=payload)
    resp.raise_for_status()
    return resp.json()

def main():
    if not API_KEY:
        print("Set PHALA_CLOUD_API_KEY environment variable")
        return

    print("=" * 60)
    print("Deploying CVM Replica with Existing App ID")
    print("=" * 60)
    print(f"Existing App ID: {EXISTING_APP_ID}")
    print(f"Target Node: prod9 (id={TARGET_NODE_ID})")
    print()

    # Step 1: Provision
    print("Step 1: Provisioning CVM resources...")
    compose_content = read_compose_file()
    provision_result = provision_cvm(
        name=REPLICA_NAME,
        compose_content=compose_content,
        node_id=TARGET_NODE_ID,
        kms_id="kms-base-prod9"
    )

    print(f"  Compose Hash: {provision_result.get('compose_hash', 'N/A')}")
    print(f"  Device ID: {provision_result.get('device_id', 'N/A')}")

    # Step 2: Create CVM with existing app_id
    print("\nStep 2: Creating CVM with existing App ID...")
    print("  (Skipping contract deployment - using existing AppAuth)")

    # Get deployer address from first CVM or use a known one
    # For allowAnyDevice=true, the deployer doesn't matter for auth
    deployer = "0x0000000000000000000000000000000000000000"  # placeholder

    try:
        create_result = create_cvm_with_existing_app(
            app_id=EXISTING_APP_ID,
            compose_hash=provision_result["compose_hash"],
            app_auth_address=EXISTING_APP_AUTH_ADDRESS,
            deployer_address=deployer
        )

        print("\nCVM Created!")
        print(json.dumps(create_result, indent=2))

    except requests.exceptions.HTTPError as e:
        print(f"\nError: {e}")
        print(f"Response: {e.response.text}")
        print("\nThis might fail if:")
        print("  1. The AppAuth contract wasn't deployed with allowAnyDevice=true")
        print("  2. The compose_hash isn't registered in the contract")
        print("  3. The device_id for prod9 isn't whitelisted")

if __name__ == "__main__":
    main()
