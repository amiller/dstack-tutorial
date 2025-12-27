#!/usr/bin/env python3
"""
Deploy CVM with allowAnyDevice=true for self-join support.

This script:
1. Provisions a CVM
2. Deploys AppAuth contract with allowAnyDevice=true
3. Creates the CVM

For replicas, use deploy_replica.py with the appId from this deployment.
"""

import os
import json
import platform
import hashlib
import requests
from pathlib import Path
from web3 import Web3
from eth_account import Account

# Decrypt API key (same as deploy_replica.py)
def get_machine_key():
    import subprocess
    hostname = platform.node()
    plat = platform.system().lower()
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
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
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
    pad_len = padded[-1]
    return padded[:-pad_len].decode()

CLOUD_API = "https://cloud-api.phala.network/api/v1"
API_KEY = os.environ.get("PHALA_CLOUD_API_KEY") or decrypt_api_key()
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")

# Base mainnet
BASE_RPC = "https://mainnet.base.org"
KMS_CONTRACT = "0x2f83172A49584C017F2B256F0FB2Dca14126Ba9C"

# KMS Factory ABI for deploying AppAuth with allowAnyDevice
KMS_FACTORY_ABI = [{
    "inputs": [
        {"name": "deployer", "type": "address"},
        {"name": "disableUpgrades", "type": "bool"},
        {"name": "allowAnyDevice", "type": "bool"},
        {"name": "deviceId", "type": "bytes32"},
        {"name": "composeHash", "type": "bytes32"}
    ],
    "name": "deployAndRegisterApp",
    "outputs": [{"name": "", "type": "address"}],
    "stateMutability": "nonpayable",
    "type": "function"
}, {
    "inputs": [
        {"name": "appId", "type": "address", "indexed": True},
        {"name": "deployer", "type": "address", "indexed": True}
    ],
    "name": "AppDeployedViaFactory",
    "type": "event"
}]

def get_headers():
    return {"X-API-Key": API_KEY, "Content-Type": "application/json"}

def read_compose_file():
    with open("docker-compose.yaml", "r") as f:
        return f.read()

def provision_cvm(name: str, compose_content: str, node_id: int, kms_id: str):
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

def deploy_app_auth_any_device(compose_hash: str):
    """Deploy AppAuth contract with allowAnyDevice=true"""
    w3 = Web3(Web3.HTTPProvider(BASE_RPC))
    account = Account.from_key(PRIVATE_KEY)

    contract = w3.eth.contract(address=KMS_CONTRACT, abi=KMS_FACTORY_ABI)

    # Zero device ID + allowAnyDevice=true
    device_id = bytes(32)
    compose_hash_bytes = bytes.fromhex(compose_hash.replace("0x", ""))

    tx = contract.functions.deployAndRegisterApp(
        account.address,      # deployer
        False,                # disableUpgrades
        True,                 # allowAnyDevice = TRUE!
        device_id,            # zero device ID
        compose_hash_bytes    # compose hash
    ).build_transaction({
        'from': account.address,
        'nonce': w3.eth.get_transaction_count(account.address),
        'gas': 500000,
        'gasPrice': w3.eth.gas_price
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"  Transaction: {tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    # Parse AppDeployedViaFactory event to get appId
    logs = contract.events.AppDeployedViaFactory().process_receipt(receipt)
    if not logs:
        raise Exception("No AppDeployedViaFactory event found")

    app_id = logs[0]['args']['appId']
    return app_id, account.address

def create_cvm(app_id: str, compose_hash: str, app_auth_address: str, deployer: str):
    payload = {
        "app_id": app_id.lower().replace("0x", ""),
        "compose_hash": compose_hash,
        "encrypted_env": "",
        "app_auth_contract_address": app_auth_address,
        "deployer_address": deployer
    }
    resp = requests.post(f"{CLOUD_API}/cvms", headers=get_headers(), json=payload)
    resp.raise_for_status()
    return resp.json()

def main():
    if not API_KEY:
        print("Set PHALA_CLOUD_API_KEY or have ~/.phala-cloud/api-key")
        return
    if not PRIVATE_KEY:
        print("Set PRIVATE_KEY environment variable (for Base contract deployment)")
        return

    print("=" * 60)
    print("Deploying CVM with allowAnyDevice=true")
    print("=" * 60)

    # Step 1: Provision
    print("\nStep 1: Provisioning CVM resources on prod5...")
    compose_content = read_compose_file()
    provision = provision_cvm("tee-oracle-any", compose_content, 26, "kms-base-prod5")
    compose_hash = provision["compose_hash"]
    print(f"  Compose Hash: {compose_hash}")

    # Step 2: Deploy AppAuth with allowAnyDevice=true
    print("\nStep 2: Deploying AppAuth contract with allowAnyDevice=true...")
    app_id, deployer = deploy_app_auth_any_device(compose_hash)
    print(f"  App ID: {app_id}")
    print(f"  Deployer: {deployer}")

    # Step 3: Create CVM
    print("\nStep 3: Creating CVM...")
    result = create_cvm(app_id, compose_hash, app_id, deployer)
    print(f"  CVM ID: {result.get('id')}")
    print(f"  Status: {result.get('status')}")

    print("\n" + "=" * 60)
    print("SUCCESS! Save this for deploying replicas:")
    print(f"  APP_ID={app_id}")
    print(f"  COMPOSE_HASH={compose_hash}")
    print("=" * 60)

if __name__ == "__main__":
    main()
