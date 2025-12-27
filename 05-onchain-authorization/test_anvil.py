#!/usr/bin/env python3
"""
Test TeeOracle.sol signature verification on local anvil.

Prerequisites:
  pip install -r requirements.txt
  phala simulator start
  docker compose up (oracle on localhost:8080)
  anvil &  (local ethereum node on localhost:8545)

Usage:
  python3 test_anvil.py
"""

import subprocess
import requests
from eth_account import Account
from eth_utils import keccak
from eth_keys import keys
from web3 import Web3

ORACLE_URL = "http://localhost:8080"
ANVIL_RPC = "http://localhost:8545"
ANVIL_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"  # anvil default

# Simulator KMS root
KMS_ROOT = "0x8f2cF602C9695b23130367ed78d8F557554de7C5"

def deploy_contract(app_id: str) -> str:
    """Deploy TeeOracle.sol using forge"""
    print("Deploying TeeOracle.sol...")

    # Convert app_id to bytes32 format (pad on right, not left - contract uses bytes20(appId))
    app_id_bytes32 = "0x" + app_id.replace("0x", "").ljust(64, '0')

    result = subprocess.run([
        "forge", "create", "TeeOracle.sol:TeeOracle",
        "--broadcast",
        "--rpc-url", ANVIL_RPC,
        "--private-key", ANVIL_PRIVATE_KEY,
        "--constructor-args", KMS_ROOT, app_id_bytes32
    ], capture_output=True, text=True, cwd="/home/amiller/projects/dstack/dstack-examples/tutorial/04-onchain-oracle")

    if result.returncode != 0:
        print(f"Deploy failed: {result.stderr}")
        raise Exception("Contract deployment failed")

    # Parse deployed address from output
    for line in result.stdout.split("\n"):
        if "Deployed to:" in line:
            addr = line.split("Deployed to:")[1].strip()
            print(f"  Contract: {addr}")
            return addr

    raise Exception("Could not parse deployed address")

def fetch_oracle():
    """Fetch signed price from oracle"""
    print("Fetching from oracle...")
    resp = requests.get(f"{ORACLE_URL}/price", timeout=10)
    resp.raise_for_status()

    info = requests.get(f"{ORACLE_URL}/", timeout=10).json()
    data = resp.json()
    data["appId"] = info["appId"]
    return data

def recover_app_pubkey(data) -> bytes:
    """Recover compressed app pubkey from app signature"""
    chain = data["signatureChain"]
    derived_pubkey = bytes.fromhex(chain["derivedPubkey"].replace("0x", ""))
    app_signature = bytes.fromhex(chain["appSignature"].replace("0x", ""))

    purpose = "ethereum"
    app_message = f"{purpose}:{derived_pubkey.hex()}"
    app_message_hash = keccak(text=app_message)

    app_sig_obj = keys.Signature(app_signature)
    app_pubkey = app_sig_obj.recover_public_key_from_msg_hash(app_message_hash)
    return app_pubkey.to_compressed_bytes()

def test_verify(contract_addr: str, data: dict, app_pubkey: bytes):
    """Call verify() on the deployed contract"""
    print("Calling verify() on-chain...")

    w3 = Web3(Web3.HTTPProvider(ANVIL_RPC))

    # TeeOracle ABI (just verify function)
    abi = [{
        "inputs": [
            {"name": "messageHash", "type": "bytes32"},
            {"name": "messageSignature", "type": "bytes"},
            {"name": "appSignature", "type": "bytes"},
            {"name": "kmsSignature", "type": "bytes"},
            {"name": "derivedCompressedPubkey", "type": "bytes"},
            {"name": "appCompressedPubkey", "type": "bytes"},
            {"name": "purpose", "type": "string"}
        ],
        "name": "verify",
        "outputs": [{"name": "isValid", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    }]

    contract = w3.eth.contract(address=contract_addr, abi=abi)

    chain = data["signatureChain"]

    result = contract.functions.verify(
        bytes.fromhex(data["messageHash"].replace("0x", "")),
        bytes.fromhex(data["signature"].replace("0x", "")),
        bytes.fromhex(chain["appSignature"].replace("0x", "")),
        bytes.fromhex(chain["kmsSignature"].replace("0x", "")),
        bytes.fromhex(chain["derivedPubkey"].replace("0x", "")),
        app_pubkey,
        "ethereum"
    ).call()

    return result

def main():
    print("TeeOracle Anvil Test")
    print("=" * 60)
    print(f"Oracle: {ORACLE_URL}")
    print(f"Anvil: {ANVIL_RPC}")
    print(f"KMS Root: {KMS_ROOT}")
    print()

    # Check anvil is running
    w3 = Web3(Web3.HTTPProvider(ANVIL_RPC))
    if not w3.is_connected():
        print("Anvil not running. Start with: anvil &")
        return False
    print(f"Anvil connected, block: {w3.eth.block_number}")

    # Fetch oracle data
    try:
        data = fetch_oracle()
        print(f"  Price: ${data['statement']['price']}")
        print(f"  App ID: {data['appId']}")
    except Exception as e:
        print(f"Failed to fetch oracle: {e}")
        return False

    # Recover app pubkey
    app_pubkey = recover_app_pubkey(data)
    print(f"  App Pubkey: {app_pubkey.hex()[:20]}...")

    # Deploy contract
    try:
        contract_addr = deploy_contract(data["appId"])
    except Exception as e:
        print(f"Deploy failed: {e}")
        return False

    # Test verification
    try:
        is_valid = test_verify(contract_addr, data, app_pubkey)
    except Exception as e:
        print(f"Verify failed: {e}")
        return False

    print()
    print("=" * 60)
    if is_valid:
        print("SUCCESS: On-chain verification passed")
        print("  - KMS signature verified")
        print("  - App signature verified")
        print("  - Message signature verified")
        return True
    else:
        print("FAILED: On-chain verification returned false")
        return False

if __name__ == "__main__":
    exit(0 if main() else 1)
