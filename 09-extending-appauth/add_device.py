#!/usr/bin/env python3
"""
Add a device to an AppAuth contract's whitelist.

Usage:
    python3 add_device.py <app_auth_address> <device_id>

The PRIVATE_KEY env var must be the owner of the AppAuth contract.
"""

import os
import sys
from web3 import Web3

BASE_RPC = "https://mainnet.base.org"

APP_AUTH_ABI = [{
    "inputs": [{"name": "deviceId", "type": "bytes32"}],
    "name": "addDevice",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
}, {
    "inputs": [{"name": "deviceId", "type": "bytes32", "indexed": False}],
    "name": "DeviceAdded",
    "type": "event"
}, {
    "inputs": [{"name": "", "type": "bytes32"}],
    "name": "allowedDeviceIds",
    "outputs": [{"name": "", "type": "bool"}],
    "stateMutability": "view",
    "type": "function"
}]

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 add_device.py <app_auth_address> <device_id>")
        print("Example: python3 add_device.py 0x5a367973... 0xabcd1234...")
        sys.exit(1)

    app_auth_address = sys.argv[1]
    device_id = sys.argv[2]

    private_key = os.environ.get("PRIVATE_KEY")
    if not private_key:
        print("Set PRIVATE_KEY environment variable (must be owner of AppAuth)")
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(BASE_RPC))
    account = w3.eth.account.from_key(private_key)

    # Normalize and checksum address
    if not app_auth_address.startswith("0x"):
        app_auth_address = "0x" + app_auth_address
    app_auth_address = w3.to_checksum_address(app_auth_address)
    if not device_id.startswith("0x"):
        device_id = "0x" + device_id

    # Ensure device_id is bytes32 (64 hex chars after 0x)
    device_id_bytes = bytes.fromhex(device_id.replace("0x", "").zfill(64))

    contract = w3.eth.contract(address=app_auth_address, abi=APP_AUTH_ABI)

    # Check if already allowed
    is_allowed = contract.functions.allowedDeviceIds(device_id_bytes).call()
    if is_allowed:
        print(f"Device {device_id} is already allowed")
        sys.exit(0)

    print(f"Adding device to AppAuth contract...")
    print(f"  AppAuth: {app_auth_address}")
    print(f"  Device:  {device_id}")
    print(f"  Owner:   {account.address}")

    tx = contract.functions.addDevice(device_id_bytes).build_transaction({
        'from': account.address,
        'nonce': w3.eth.get_transaction_count(account.address),
        'gas': 100000,
        'gasPrice': w3.eth.gas_price
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"  Transaction: {tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status == 1:
        print(f"  ✅ Device added successfully")
    else:
        print(f"  ❌ Transaction failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
