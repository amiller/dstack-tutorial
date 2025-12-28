#!/usr/bin/env python3
"""
Test TimelockAppAuth on Phala Cloud + Base.

Prerequisites:
  pip install eth-account web3 requests
  export PRIVATE_KEY="0x..."  (owner of the TimelockAppAuth contract)

Usage:
  # After deploying with deploy_timelock.py
  python3 test_phalacloud.py <contract_address> <oracle_url>

  # Example:
  python3 test_phalacloud.py 0x1234... https://abc-8080.dstack-prod5.phala.network
"""

import os
import sys
import time
import requests
from web3 import Web3
from eth_account import Account

BASE_RPC = "https://mainnet.base.org"
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")

CONTRACT_ABI = [
    {"inputs": [], "name": "noticePeriod", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "", "type": "bytes32"}], "name": "allowedComposeHashes", "outputs": [{"type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "", "type": "bytes32"}], "name": "proposedAt", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "hash", "type": "bytes32"}], "name": "proposeComposeHash", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "hash", "type": "bytes32"}], "name": "activateComposeHash", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "hash", "type": "bytes32"}], "name": "activatesAt", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
]

def check_oracle(oracle_url):
    """Check if oracle is running and getting keys from KMS"""
    try:
        resp = requests.get(f"{oracle_url}/", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            print(f"  Oracle running: appId={data.get('appId', 'unknown')[:16]}...")
            return True
        else:
            print(f"  Oracle returned: {resp.status_code}")
            return False
    except Exception as e:
        print(f"  Oracle error: {e}")
        return False

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 test_phalacloud.py <contract_address> <oracle_url>")
        return False

    contract_addr = sys.argv[1]
    oracle_url = sys.argv[2]

    if not PRIVATE_KEY:
        print("Set PRIVATE_KEY environment variable")
        return False

    print("TimelockAppAuth Test (Phala Cloud + Base)")
    print("=" * 60)

    w3 = Web3(Web3.HTTPProvider(BASE_RPC))
    account = Account.from_key(PRIVATE_KEY)
    contract = w3.eth.contract(address=contract_addr, abi=CONTRACT_ABI)

    print(f"Contract: {contract_addr}")
    print(f"Oracle URL: {oracle_url}")
    print(f"Owner: {account.address}")

    # Check notice period
    notice_period = contract.functions.noticePeriod().call()
    print(f"Notice Period: {notice_period} seconds")

    # Check oracle is running
    print("\n1. Checking oracle status...")
    if not check_oracle(oracle_url):
        print("  WARNING: Oracle not responding (may still be booting)")

    # Create a new test compose hash
    test_hash = w3.keccak(text=f"test-{int(time.time())}")
    print(f"\n2. Proposing test compose hash...")
    print(f"  Hash: {test_hash.hex()}")

    # Check it's not already active
    if contract.functions.allowedComposeHashes(test_hash).call():
        print("  Already active (unexpected)")
        return False

    # Propose
    tx = contract.functions.proposeComposeHash(test_hash).build_transaction({
        'from': account.address,
        'nonce': w3.eth.get_transaction_count(account.address),
        'gas': 100000,
        'gasPrice': w3.eth.gas_price
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt["status"] != 1:
        print("  Propose failed!")
        return False

    proposed_at = contract.functions.proposedAt(test_hash).call()
    activates_at = contract.functions.activatesAt(test_hash).call()
    print(f"  ✓ Proposed at: {proposed_at}")
    print(f"  ✓ Activates at: {activates_at}")

    # Calculate wait time
    current_time = w3.eth.get_block('latest')['timestamp']
    wait_time = max(0, activates_at - current_time)

    if wait_time > 0:
        print(f"\n3. Waiting {wait_time} seconds for notice period...")
        time.sleep(wait_time + 5)  # Extra 5 seconds for block time

    # Activate
    print("\n4. Activating...")
    tx = contract.functions.activateComposeHash(test_hash).build_transaction({
        'from': account.address,
        'nonce': w3.eth.get_transaction_count(account.address),
        'gas': 100000,
        'gasPrice': w3.eth.gas_price
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt["status"] != 1:
        print("  Activation failed!")
        return False

    # Verify active
    if not contract.functions.allowedComposeHashes(test_hash).call():
        print("  Hash not active after activation!")
        return False

    print("  ✓ Hash is now active")

    print("\n" + "=" * 60)
    print("SUCCESS: Timelock flow verified on Base mainnet")
    print("  - Proposed new compose hash")
    print("  - Waited for notice period")
    print("  - Activated after delay")
    print()
    print("The CVM can now use this compose hash to get keys from KMS.")
    return True

if __name__ == "__main__":
    exit(0 if main() else 1)
