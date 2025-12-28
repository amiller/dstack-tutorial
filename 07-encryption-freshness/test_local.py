#!/usr/bin/env python3
import requests
import uuid

BASE = "http://localhost:8080"

def main():
    print("Testing Encrypted Notes Storage")
    print("=" * 50)

    # Generate unique key for this test
    test_key = f"test-{uuid.uuid4().hex[:8]}"
    secret_content = "This is my secret message that gets encrypted!"

    # Store a note
    print(f"\n1. Storing note with key: {test_key}")
    resp = requests.post(f"{BASE}/notes/{test_key}", json={"content": secret_content})
    data = resp.json()
    print(f"   Stored: {data['stored']}")
    print(f"   Ciphertext length: {data['ciphertext_len']} bytes")

    # Retrieve the note
    print(f"\n2. Retrieving note")
    resp = requests.get(f"{BASE}/notes/{test_key}")
    data = resp.json()
    print(f"   Content: {data['content']}")

    # Verify content matches
    assert data["content"] == secret_content, "Content mismatch!"
    print("   OK: Content matches original")

    # List all keys
    print(f"\n3. Listing all keys")
    resp = requests.get(f"{BASE}/notes")
    data = resp.json()
    print(f"   Keys: {data['keys']}")
    assert test_key in data["keys"], "Key not in list!"

    # Delete the note
    print(f"\n4. Deleting note")
    resp = requests.delete(f"{BASE}/notes/{test_key}")
    data = resp.json()
    print(f"   Deleted: {data['deleted']}")

    # Verify deletion
    print(f"\n5. Verifying deletion")
    resp = requests.get(f"{BASE}/notes/{test_key}")
    assert resp.status_code == 404, "Note should be deleted!"
    print("   OK: Note no longer exists")

    print("\n" + "=" * 50)
    print("All tests passed!")
    print("\nNote: The database only ever saw encrypted bytes.")
    print("Decryption happens inside the TEE using a KMS-derived key.")

if __name__ == "__main__":
    main()
