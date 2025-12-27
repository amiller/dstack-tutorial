#!/usr/bin/env python3
"""
Production test for TEE Oracle on Phala Cloud.

Prerequisites:
  pip install eth-account eth-keys requests web3

Usage:
  # Set your CVM URL after deploying
  export ORACLE_URL="https://<app-id>-8080.dstack-base-prod7.phala.network"
  python test_production.py

  # Or pass as argument
  python test_production.py https://<your-cvm-url>
"""

import json
import os
import sys
import requests
from eth_account import Account
from eth_utils import keccak
from eth_keys import keys
from web3 import Web3

# Phala Cloud KMS contract on Base
KMS_CONTRACT_ADDRESS = "0x2f83172A49584C017F2B256F0FB2Dca14126Ba9C"
BASE_RPC_URL = "https://mainnet.base.org"

def get_kms_root_from_contract():
    """Get KMS root address from the on-chain KMS contract"""
    print("🔑 Getting KMS Root from Contract")
    print("=" * 50)

    w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
    print(f"🔗 Base connection: {w3.is_connected()}")

    kms_abi = [{
        "inputs": [],
        "name": "kmsInfo",
        "outputs": [
            {"name": "k256Pubkey", "type": "bytes"},
            {"name": "rsaPubkey", "type": "bytes"}
        ],
        "type": "function"
    }]

    contract = w3.eth.contract(address=KMS_CONTRACT_ADDRESS, abi=kms_abi)
    k256_pubkey, _ = contract.functions.kmsInfo().call()

    print(f"📋 KMS Contract: {KMS_CONTRACT_ADDRESS}")
    print(f"📋 K256 Pubkey: 0x{k256_pubkey.hex()[:20]}...")

    # Derive address from compressed public key
    pubkey = keys.PublicKey.from_compressed_bytes(k256_pubkey)
    kms_root_address = pubkey.to_checksum_address()

    print(f"✅ KMS Root Address: {kms_root_address}")
    return kms_root_address

def fetch_oracle_price(oracle_url):
    """Fetch signed price from oracle"""
    print(f"\n📡 Fetching from {oracle_url}/price...")
    resp = requests.get(f"{oracle_url}/price", timeout=30)
    resp.raise_for_status()
    return resp.json()

def fetch_oracle_info(oracle_url):
    """Fetch oracle info including app_id"""
    resp = requests.get(f"{oracle_url}/", timeout=10)
    resp.raise_for_status()
    return resp.json()

def verify_signature_chain(data, app_id, expected_kms_root):
    """Verify the complete signature chain"""
    print("\n🔐 Verifying Signature Chain")
    print("=" * 50)

    chain = data["signatureChain"]
    derived_pubkey = bytes.fromhex(chain["derivedPubkey"].replace("0x", ""))
    app_signature = bytes.fromhex(chain["appSignature"].replace("0x", ""))
    kms_signature = bytes.fromhex(chain["kmsSignature"].replace("0x", ""))
    message_hash = bytes.fromhex(data["messageHash"].replace("0x", ""))
    message_signature = bytes.fromhex(data["signature"].replace("0x", ""))
    app_id_bytes = bytes.fromhex(app_id.replace("0x", ""))

    print(f"App ID: {app_id}")
    print(f"Expected KMS Root: {expected_kms_root}")

    # Step 1: Verify app signature over derived key
    purpose = "ethereum"
    app_message = f"{purpose}:{derived_pubkey.hex()}"
    app_message_hash = keccak(text=app_message)

    app_sig_obj = keys.Signature(app_signature)
    app_pubkey = app_sig_obj.recover_public_key_from_msg_hash(app_message_hash)
    app_pubkey_compressed = app_pubkey.to_compressed_bytes()
    app_address = app_pubkey.to_checksum_address()

    print(f"\n✓ Step 1: App signature recovered")
    print(f"  App Address: {app_address}")

    # Step 2: Verify KMS signature over app key
    kms_message = b"dstack-kms-issued:" + app_id_bytes + app_pubkey_compressed
    kms_message_hash = keccak(kms_message)

    kms_signer = Account._recover_hash(kms_message_hash, signature=kms_signature)

    print(f"\n✓ Step 2: KMS signature")
    print(f"  Recovered KMS: {kms_signer}")
    print(f"  Expected KMS:  {expected_kms_root}")

    if kms_signer.lower() != expected_kms_root.lower():
        print("  ❌ KMS signature FAILED!")
        return False, None

    print("  ✅ KMS signature verified!")

    # Step 3: Verify message signature
    eth_message = b"\x19Ethereum Signed Message:\n32" + message_hash
    eth_hash = keccak(eth_message)

    message_signer = Account._recover_hash(eth_hash, signature=message_signature)

    derived_key_obj = keys.PublicKey.from_compressed_bytes(derived_pubkey)
    expected_signer = derived_key_obj.to_checksum_address()

    print(f"\n✓ Step 3: Message signature")
    print(f"  Recovered signer: {message_signer}")
    print(f"  Expected signer:  {expected_signer}")

    if message_signer.lower() != expected_signer.lower():
        print("  ❌ Message signature FAILED!")
        return False, None

    print("  ✅ Message signature verified!")

    # Return data needed for on-chain verification
    return True, {
        "app_pubkey_compressed": app_pubkey_compressed,
        "derived_pubkey": derived_pubkey,
        "app_signature": app_signature,
        "kms_signature": kms_signature,
        "message_hash": message_hash,
        "message_signature": message_signature,
        "app_id": app_id_bytes
    }

def main():
    print("🚀 TEE Oracle Production Test (Phala Cloud)")
    print("=" * 60)

    # Get oracle URL
    oracle_url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("ORACLE_URL")
    if not oracle_url:
        print("❌ No oracle URL provided")
        print("\nUsage:")
        print("  export ORACLE_URL='https://<app-id>-8080.dstack-prod.phala.network'")
        print("  python test_production.py")
        print("\nOr:")
        print("  python test_production.py <oracle-url>")
        return False

    print(f"Oracle URL: {oracle_url}")
    print()

    # Step 1: Get KMS root from contract
    try:
        kms_root = get_kms_root_from_contract()
    except Exception as e:
        print(f"❌ Failed to get KMS root: {e}")
        return False

    # Step 2: Fetch oracle data
    try:
        data = fetch_oracle_price(oracle_url)
        info = fetch_oracle_info(oracle_url)
        app_id = info["appId"]

        print(f"✅ Got price: ${data['statement']['price']}")
        print(f"   Source: {data['statement']['source']}")
        print(f"   App ID: {app_id}")
    except Exception as e:
        print(f"❌ Failed to fetch oracle: {e}")
        return False

    # Step 3: Verify signature chain
    success, chain_data = verify_signature_chain(data, app_id, kms_root)

    if success:
        print("\n" + "=" * 60)
        print("🎉 Production verification passed!")
        print("   ✅ KMS contract confirmed the root key")
        print("   ✅ Signature chain verified")
        print("   ✅ Oracle message authenticated")
        print()
        print("This output can be verified on-chain with TeeOracle.sol")
        print(f"Deploy with: kmsRoot={kms_root}, appId=0x{app_id}")
        return True
    else:
        print("\n❌ Verification failed!")
        return False

if __name__ == "__main__":
    main()
