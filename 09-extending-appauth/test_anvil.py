#!/usr/bin/env python3
"""
Test TimelockAppAuth.sol propose/activate flow on local anvil.

Prerequisites:
  anvil &  (local ethereum node on localhost:8545)

Usage:
  python3 test_anvil.py
"""

import subprocess
import time
from web3 import Web3

ANVIL_RPC = "http://localhost:8545"
ANVIL_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

CONTRACT_ABI = [
    {"inputs": [{"name": "_noticePeriod", "type": "uint256"}, {"name": "_allowAnyDevice", "type": "bool"}, {"name": "initialComposeHash", "type": "bytes32"}], "stateMutability": "nonpayable", "type": "constructor"},
    {"inputs": [{"name": "hash", "type": "bytes32"}], "name": "proposeComposeHash", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "hash", "type": "bytes32"}], "name": "activateComposeHash", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "hash", "type": "bytes32"}], "name": "activatesAt", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "", "type": "bytes32"}], "name": "allowedComposeHashes", "outputs": [{"name": "", "type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "", "type": "bytes32"}], "name": "proposedAt", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "noticePeriod", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"type": "event", "name": "ComposeHashProposed", "inputs": [{"indexed": True, "name": "hash", "type": "bytes32"}, {"indexed": False, "name": "activatesAt", "type": "uint256"}]},
    {"type": "event", "name": "ComposeHashActivated", "inputs": [{"indexed": True, "name": "hash", "type": "bytes32"}]},
]

NOTICE_PERIOD = 10  # 10 seconds for test
INITIAL_HASH = "0x" + "01" * 32
NEW_HASH = "0x" + "02" * 32

def deploy_contract() -> str:
    print("Deploying TimelockAppAuth.sol...")
    result = subprocess.run([
        "forge", "create", "TimelockAppAuth.sol:TimelockAppAuth",
        "--broadcast", "--rpc-url", ANVIL_RPC,
        "--private-key", ANVIL_PRIVATE_KEY,
        "--constructor-args", str(NOTICE_PERIOD), "true", INITIAL_HASH
    ], capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Deploy failed: {result.stderr}")
    for line in result.stdout.split("\n"):
        if "Deployed to:" in line:
            return line.split("Deployed to:")[1].strip()
    raise Exception("Could not parse deployed address")

def main():
    print("TimelockAppAuth Test")
    print("=" * 60)

    w3 = Web3(Web3.HTTPProvider(ANVIL_RPC))
    if not w3.is_connected():
        print("Start anvil first: anvil &")
        return False
    print(f"Anvil block: {w3.eth.block_number}")

    account = w3.eth.account.from_key(ANVIL_PRIVATE_KEY)

    # Deploy contract
    contract_addr = deploy_contract()
    print(f"  Contract: {contract_addr}")
    print(f"  Notice period: {NOTICE_PERIOD} seconds")
    contract = w3.eth.contract(address=contract_addr, abi=CONTRACT_ABI)

    # Verify initial hash is active
    print("\n1. Checking initial hash is active...")
    assert contract.functions.allowedComposeHashes(INITIAL_HASH).call(), "Initial hash should be active"
    print("  ✓ Initial hash is active")

    # Propose new hash
    print("\n2. Proposing new compose hash...")
    tx = contract.functions.proposeComposeHash(NEW_HASH).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 100000,
        "gasPrice": w3.eth.gas_price
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    assert receipt["status"] == 1, "Propose failed"

    proposed_at = contract.functions.proposedAt(NEW_HASH).call()
    activates_at = contract.functions.activatesAt(NEW_HASH).call()
    print(f"  ✓ Proposed at block timestamp: {proposed_at}")
    print(f"  ✓ Activates at: {activates_at}")

    # Try to activate too early (should fail)
    print("\n3. Trying to activate before notice period (should fail)...")
    try:
        tx = contract.functions.activateComposeHash(NEW_HASH).build_transaction({
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": 100000,
            "gasPrice": w3.eth.gas_price
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt["status"] == 1:
            print("  ✗ ERROR: Early activation should have failed!")
            return False
    except Exception as e:
        if "notice period not elapsed" in str(e):
            print("  ✓ Correctly rejected: notice period not elapsed")
        else:
            print(f"  ✓ Rejected (tx reverted)")

    # Wait for notice period
    print(f"\n4. Waiting {NOTICE_PERIOD} seconds for notice period...")
    time.sleep(NOTICE_PERIOD + 1)

    # Mine a block to update timestamp (anvil auto-mines, but let's be sure)
    w3.provider.make_request("evm_mine", [])

    # Activate after notice period
    print("\n5. Activating after notice period...")
    tx = contract.functions.activateComposeHash(NEW_HASH).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 100000,
        "gasPrice": w3.eth.gas_price
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt["status"] != 1:
        print("  ✗ ERROR: Activation failed after notice period!")
        return False

    # Verify new hash is now active
    assert contract.functions.allowedComposeHashes(NEW_HASH).call(), "New hash should be active"
    print("  ✓ New hash is now active")

    print("\n" + "=" * 60)
    print("SUCCESS: Timelock flow complete")
    print("  - Initial hash was active at deployment")
    print("  - Proposed new hash, started notice period")
    print("  - Early activation correctly rejected")
    print("  - Activated after notice period elapsed")
    return True

if __name__ == "__main__":
    exit(0 if main() else 1)
