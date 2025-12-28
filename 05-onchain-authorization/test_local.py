#!/usr/bin/env python3
"""
Local test for TEE Oracle signature chain verification.

Prerequisites:
  pip install eth-account eth-keys requests web3
  phala simulator start
  docker compose up (oracle running on localhost:8080)

Optionally for on-chain testing:
  anvil &  (local ethereum node)
  forge script to deploy TeeOracle.sol
"""

import json
import requests
from eth_account import Account
from eth_utils import keccak
from eth_keys import keys

# Simulator KMS root address (recovered from k256_signature in appkeys.json)
# Note: k256_key in appkeys.json is the APP key, not KMS root
# The KMS root is whoever signed that app key
KMS_ROOT_ADDRESS = "0x8f2cF602C9695b23130367ed78d8F557554de7C5"

ORACLE_URL = "http://localhost:8080"

def fetch_oracle_price():
    """Fetch signed price from oracle"""
    print("📡 Fetching from oracle...")
    resp = requests.get(f"{ORACLE_URL}/price", timeout=10)
    resp.raise_for_status()
    return resp.json()

def verify_signature_chain(data, expected_kms_root):
    """
    Verify the complete signature chain:
    1. App key signed derived key
    2. KMS root signed app key
    3. Derived key signed the message
    """
    print("\n🔐 Verifying Signature Chain")
    print("=" * 50)

    chain = data["signatureChain"]
    derived_pubkey = bytes.fromhex(chain["derivedPubkey"].replace("0x", ""))
    app_signature = bytes.fromhex(chain["appSignature"].replace("0x", ""))
    kms_signature = bytes.fromhex(chain["kmsSignature"].replace("0x", ""))
    message_hash = bytes.fromhex(data["messageHash"].replace("0x", ""))
    message_signature = bytes.fromhex(data["signature"].replace("0x", ""))

    # Get app_id from oracle info
    info_resp = requests.get(f"{ORACLE_URL}/", timeout=10)
    app_id = info_resp.json()["appId"]
    app_id_bytes = bytes.fromhex(app_id.replace("0x", ""))

    print(f"App ID: {app_id}")
    print(f"Derived Pubkey: {derived_pubkey.hex()[:20]}...")
    print(f"Expected KMS Root: {expected_kms_root}")

    # Step 1: Verify app signature over derived key
    # Message format: "{purpose}:{derived_pubkey_hex}"
    purpose = "ethereum"
    app_message = f"{purpose}:{derived_pubkey.hex()}"
    app_message_hash = keccak(text=app_message)

    # Recover app key from signature
    app_sig_obj = keys.Signature(app_signature)
    app_pubkey = app_sig_obj.recover_public_key_from_msg_hash(app_message_hash)
    app_pubkey_compressed = app_pubkey.to_compressed_bytes()
    app_address = app_pubkey.to_checksum_address()

    print(f"\n✓ Step 1: App signature")
    print(f"  App Address: {app_address}")

    # Step 2: Verify KMS signature over app key
    # Message format: "dstack-kms-issued:" + app_id + app_pubkey_sec1
    kms_message = b"dstack-kms-issued:" + app_id_bytes + app_pubkey_compressed
    kms_message_hash = keccak(kms_message)

    kms_signer = Account._recover_hash(kms_message_hash, signature=kms_signature)

    print(f"\n✓ Step 2: KMS signature")
    print(f"  Recovered KMS: {kms_signer}")
    print(f"  Expected KMS:  {expected_kms_root}")

    if kms_signer.lower() != expected_kms_root.lower():
        print("  ❌ KMS signature FAILED!")
        return False

    print("  ✅ KMS signature verified!")

    # Step 3: Verify message signature
    # Uses EIP-191 personal sign
    eth_message = b"\x19Ethereum Signed Message:\n32" + message_hash
    eth_hash = keccak(eth_message)

    message_signer = Account._recover_hash(eth_hash, signature=message_signature)

    # Get expected signer from derived pubkey
    derived_key_obj = keys.PublicKey.from_compressed_bytes(derived_pubkey)
    expected_signer = derived_key_obj.to_checksum_address()

    print(f"\n✓ Step 3: Message signature")
    print(f"  Recovered signer: {message_signer}")
    print(f"  Expected signer:  {expected_signer}")

    if message_signer.lower() != expected_signer.lower():
        print("  ❌ Message signature FAILED!")
        return False

    print("  ✅ Message signature verified!")

    return True

def main():
    print("🚀 TEE Oracle Local Test")
    print("=" * 60)
    print(f"Oracle URL: {ORACLE_URL}")
    print(f"KMS Root: {KMS_ROOT_ADDRESS}")
    print()

    # Fetch oracle data
    try:
        data = fetch_oracle_price()
        print(f"Got price: ${data['price'] / 100:.2f}")
        print(f"Source: {data['source']}")
        print(f"TLS Fingerprint: {data['tlsFingerprint'][:30]}...")
    except Exception as e:
        print(f"❌ Failed to fetch oracle: {e}")
        print("\nMake sure the oracle is running:")
        print("  docker compose run --rm -p 8080:8080 \\")
        print("    -v ~/.phala-cloud/simulator/0.5.3/dstack.sock:/var/run/dstack.sock app")
        return False

    # Verify signature chain
    if verify_signature_chain(data, KMS_ROOT_ADDRESS):
        print("\n" + "=" * 60)
        print("🎉 All verifications passed!")
        print("   ✅ KMS signed the app key")
        print("   ✅ App key signed the derived key")
        print("   ✅ Derived key signed the oracle message")
        print("\nThis oracle output can be verified on-chain.")
        return True
    else:
        print("\n❌ Verification failed!")
        return False

if __name__ == "__main__":
    main()
