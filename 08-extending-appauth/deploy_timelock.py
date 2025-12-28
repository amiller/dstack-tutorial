#!/usr/bin/env python3
"""
Deploy CVM with TimelockAppAuth for on-chain due diligence.

This script:
1. Provisions a CVM to get compose_hash
2. Deploys TimelockAppAuth contract to Base
3. Registers app with KMS
4. Creates the CVM

The timelock enforces a notice period before new compose hashes activate.
"""

import os
import json
import subprocess
import platform
import hashlib
import requests
from pathlib import Path
from web3 import Web3
from eth_account import Account

# Decrypt API key
def get_machine_key():
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

COMPOSE_FILE_NAME = "timelock-oracle"
NOTICE_PERIOD = 120  # 2 minutes for demo

# Base mainnet
BASE_RPC = "https://mainnet.base.org"
KMS_CONTRACT = "0x2f83172A49584C017F2B256F0FB2Dca14126Ba9C"

# KMS ABI for registering custom app
KMS_ABI = [{
    "inputs": [{"name": "appAuth", "type": "address"}],
    "name": "registerApp",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
}, {
    "inputs": [{"name": "appId", "type": "address", "indexed": True}],
    "name": "AppRegistered",
    "type": "event"
}]

def get_headers():
    return {"X-API-Key": API_KEY, "Content-Type": "application/json"}

def read_compose_file():
    compose_path = Path(__file__).parent.parent / "05-onchain-authorization" / "docker-compose.yaml"
    with open(compose_path, "r") as f:
        return f.read()

def provision_cvm(cvm_name: str, compose_name: str, compose_content: str, node_id: int, kms_id: str):
    payload = {
        "name": cvm_name,
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
            "name": compose_name,
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

BASESCAN_API_KEY = os.environ.get("BASESCAN_API_KEY")

def deploy_timelock_contract(compose_hash: str):
    """Deploy TimelockAppAuth to Base using forge"""
    print(f"  Deploying with notice period: {NOTICE_PERIOD} seconds")

    cmd = [
        "forge", "create", "TimelockAppAuth.sol:TimelockAppAuth",
        "--broadcast", "--rpc-url", BASE_RPC,
        "--private-key", PRIVATE_KEY,
        "--constructor-args",
        str(NOTICE_PERIOD),  # noticePeriod
        "true",              # allowAnyDevice
        compose_hash         # initialComposeHash
    ]

    # Add verification if API key available
    if BASESCAN_API_KEY:
        cmd.extend(["--verify", "--etherscan-api-key", BASESCAN_API_KEY])

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(f"Deploy failed: {result.stderr}")

    for line in result.stdout.split("\n"):
        if "Deployed to:" in line:
            addr = line.split("Deployed to:")[1].strip()
            if not BASESCAN_API_KEY:
                print(f"  (Run 'forge verify-contract {addr} TimelockAppAuth.sol:TimelockAppAuth --chain base' to verify)")
            return addr
    raise Exception("Could not parse deployed address")

def register_app(app_auth_address: str):
    """Register the custom AppAuth contract with KMS"""
    w3 = Web3(Web3.HTTPProvider(BASE_RPC))
    account = Account.from_key(PRIVATE_KEY)
    contract = w3.eth.contract(address=KMS_CONTRACT, abi=KMS_ABI)

    tx = contract.functions.registerApp(app_auth_address).build_transaction({
        'from': account.address,
        'nonce': w3.eth.get_transaction_count(account.address),
        'gas': 200000,
        'gasPrice': w3.eth.gas_price
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"  Register tx: {tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt["status"] != 1:
        raise Exception("Registration failed")
    return receipt

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

    w3 = Web3(Web3.HTTPProvider(BASE_RPC))
    account = Account.from_key(PRIVATE_KEY)

    print("=" * 60)
    print("Deploying CVM with TimelockAppAuth")
    print("=" * 60)
    print(f"Deployer: {account.address}")
    print(f"Notice Period: {NOTICE_PERIOD} seconds")
    print(f"Compose File Name: {COMPOSE_FILE_NAME}")

    # Step 1: Provision
    print("\nStep 1: Provisioning CVM resources...")
    compose_content = read_compose_file()
    import time
    cvm_name = f"timelock-oracle-{int(time.time()) % 10000}"
    provision = provision_cvm(
        cvm_name=cvm_name,
        compose_name=COMPOSE_FILE_NAME,
        compose_content=compose_content,
        node_id=26,
        kms_id="kms-base-prod5"
    )
    compose_hash = provision["compose_hash"]
    print(f"  Compose Hash: {compose_hash}")

    # Step 2: Deploy TimelockAppAuth
    print("\nStep 2: Deploying TimelockAppAuth to Base...")
    app_auth_address = deploy_timelock_contract(compose_hash)
    print(f"  Contract: {app_auth_address}")

    # Step 3: Register with KMS
    print("\nStep 3: Registering app with KMS...")
    register_app(app_auth_address)
    print(f"  Registered!")

    # Step 4: Create CVM
    print("\nStep 4: Creating CVM...")
    result = create_cvm(app_auth_address, compose_hash, app_auth_address, account.address)
    print(f"  CVM ID: {result.get('id')}")
    print(f"  Status: {result.get('status')}")

    print("\n" + "=" * 60)
    print("SUCCESS!")
    print(f"  App Auth (TimelockAppAuth): {app_auth_address}")
    print(f"  Compose Hash: {compose_hash}")
    print(f"  Notice Period: {NOTICE_PERIOD} seconds")
    print()
    print("To propose a new compose hash:")
    print(f"  cast send {app_auth_address} 'proposeComposeHash(bytes32)' <NEW_HASH> \\")
    print(f"    --private-key $PRIVATE_KEY --rpc-url {BASE_RPC}")
    print()
    print("After notice period, activate:")
    print(f"  cast send {app_auth_address} 'activateComposeHash(bytes32)' <NEW_HASH> \\")
    print(f"    --private-key $PRIVATE_KEY --rpc-url {BASE_RPC}")
    print("=" * 60)

if __name__ == "__main__":
    main()
