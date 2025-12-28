#!/usr/bin/env python3
"""
Test TeeOracle.sol request/fulfill flow on local anvil.

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
from eth_keys import keys
from eth_utils import keccak
from web3 import Web3

ORACLE_URL = "http://localhost:8080"
ANVIL_RPC = "http://localhost:8545"
ANVIL_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
KMS_ROOT = "0x8f2cF602C9695b23130367ed78d8F557554de7C5"

CONTRACT_ABI = [
    {"inputs": [{"name": "_kmsRoot", "type": "address"}, {"name": "_appId", "type": "bytes32"}], "stateMutability": "nonpayable", "type": "constructor"},
    {"inputs": [], "name": "request", "outputs": [{"name": "requestId", "type": "uint256"}], "stateMutability": "payable", "type": "function"},
    {"inputs": [{"name": "", "type": "uint256"}], "name": "requests", "outputs": [{"name": "requester", "type": "address"}, {"name": "reward", "type": "uint256"}, {"name": "timestamp", "type": "uint256"}, {"name": "fulfilled", "type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [
        {"name": "requestId", "type": "uint256"},
        {"name": "price", "type": "uint256"},
        {"name": "priceTimestamp", "type": "uint256"},
        {"components": [
            {"name": "messageHash", "type": "bytes32"},
            {"name": "messageSignature", "type": "bytes"},
            {"name": "appSignature", "type": "bytes"},
            {"name": "kmsSignature", "type": "bytes"},
            {"name": "derivedCompressedPubkey", "type": "bytes"},
            {"name": "appCompressedPubkey", "type": "bytes"},
            {"name": "purpose", "type": "string"}
        ], "name": "proof", "type": "tuple"}
    ], "name": "fulfill", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"type": "event", "name": "RequestCreated", "inputs": [{"indexed": True, "name": "requestId", "type": "uint256", "internalType": "uint256"}, {"indexed": True, "name": "requester", "type": "address", "internalType": "address"}, {"indexed": False, "name": "reward", "type": "uint256", "internalType": "uint256"}], "anonymous": False},
    {"type": "event", "name": "RequestFulfilled", "inputs": [{"indexed": True, "name": "requestId", "type": "uint256", "internalType": "uint256"}, {"indexed": False, "name": "price", "type": "uint256", "internalType": "uint256"}, {"indexed": False, "name": "fulfiller", "type": "address", "internalType": "address"}], "anonymous": False},
]

def deploy_contract(app_id: str) -> str:
    print("Deploying TeeOracle.sol...")
    app_id_bytes32 = "0x" + app_id.replace("0x", "").ljust(64, '0')
    result = subprocess.run([
        "forge", "create", "TeeOracle.sol:TeeOracle",
        "--broadcast", "--rpc-url", ANVIL_RPC,
        "--private-key", ANVIL_PRIVATE_KEY,
        "--constructor-args", KMS_ROOT, app_id_bytes32
    ], capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Deploy failed: {result.stderr}")
    for line in result.stdout.split("\n"):
        if "Deployed to:" in line:
            return line.split("Deployed to:")[1].strip()
    raise Exception("Could not parse deployed address")

def fetch_oracle():
    print("Fetching oracle price...")
    info = requests.get(f"{ORACLE_URL}/", timeout=10).json()
    data = requests.get(f"{ORACLE_URL}/price", timeout=10).json()
    data["appId"] = info["appId"]
    return data

def recover_app_pubkey(data) -> bytes:
    chain = data["signatureChain"]
    derived_pubkey = bytes.fromhex(chain["derivedPubkey"].replace("0x", ""))
    app_signature = bytes.fromhex(chain["appSignature"].replace("0x", ""))
    app_message = f"ethereum:{derived_pubkey.hex()}"
    app_message_hash = keccak(text=app_message)
    app_sig_obj = keys.Signature(app_signature)
    return app_sig_obj.recover_public_key_from_msg_hash(app_message_hash).to_compressed_bytes()

def main():
    print("TeeOracle Request/Fulfill Test")
    print("=" * 60)

    w3 = Web3(Web3.HTTPProvider(ANVIL_RPC))
    if not w3.is_connected():
        print("Start anvil first: anvil &")
        return False
    print(f"Anvil block: {w3.eth.block_number}")

    account = w3.eth.account.from_key(ANVIL_PRIVATE_KEY)

    # Fetch oracle
    data = fetch_oracle()
    print(f"  Price: ${data['price'] / 100:.2f}")
    print(f"  Timestamp: {data['timestamp']}")
    print(f"  App ID: {data['appId']}")

    # Deploy contract
    contract_addr = deploy_contract(data["appId"])
    print(f"  Contract: {contract_addr}")
    contract = w3.eth.contract(address=contract_addr, abi=CONTRACT_ABI)

    # Post request with 0.01 ETH reward
    print("\nPosting price request with 0.01 ETH reward...")
    reward = w3.to_wei(0.01, "ether")
    tx = contract.functions.request().build_transaction({
        "from": account.address,
        "value": reward,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 200000,
        "gasPrice": w3.eth.gas_price
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    # Parse request_id from logs (indexed parameter is in topics[1])
    if not receipt["logs"]:
        print(f"  ERROR: No logs in receipt. Status: {receipt['status']}")
        print(f"  Receipt: {dict(receipt)}")
        return False
    request_id = int(receipt["logs"][0]["topics"][1].hex(), 16)
    print(f"  Request ID: {request_id}")
    print(f"  Reward: {w3.from_wei(reward, 'ether')} ETH")

    # Build proof struct
    chain = data["signatureChain"]
    app_pubkey = recover_app_pubkey(data)
    proof = (
        bytes.fromhex(data["messageHash"].replace("0x", "")),
        bytes.fromhex(data["signature"].replace("0x", "")),
        bytes.fromhex(chain["appSignature"].replace("0x", "")),
        bytes.fromhex(chain["kmsSignature"].replace("0x", "")),
        bytes.fromhex(chain["derivedPubkey"].replace("0x", "")),
        app_pubkey,
        "ethereum"
    )

    # Fulfill request
    print("\nFulfilling request...")
    balance_before = w3.eth.get_balance(account.address)

    tx = contract.functions.fulfill(
        request_id,
        data["price"],
        data["timestamp"],
        proof
    ).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 500000,
        "gasPrice": w3.eth.gas_price
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt["status"] != 1:
        print("FAILED: Transaction reverted")
        return False

    # Check fulfillment
    balance_after = w3.eth.get_balance(account.address)
    gas_cost = receipt["gasUsed"] * w3.eth.gas_price

    print(f"  Fulfilled price: ${data['price'] / 100:.2f}")
    print(f"  Reward received: {w3.from_wei(balance_after - balance_before + gas_cost, 'ether'):.4f} ETH")

    # Verify request is marked fulfilled
    req = contract.functions.requests(request_id).call()
    if not req[3]:  # fulfilled flag
        print("FAILED: Request not marked as fulfilled")
        return False

    print("\n" + "=" * 60)
    print("SUCCESS: Oracle request/fulfill cycle complete")
    print("  - Posted request with ETH reward")
    print("  - Oracle signed price verified on-chain")
    print("  - Reward claimed by fulfiller")
    return True

if __name__ == "__main__":
    exit(0 if main() else 1)
