import os
import json
from flask import Flask, request, jsonify
from nacl.secret import SecretBox
import psycopg2

from dstack_sdk import DstackClient

app = Flask(__name__)

client = DstackClient()
result = client.get_key("/notes", "encryption")
key = result.decode_key()[:32]
box = SecretBox(key)

print(f"Encryption key derived from KMS")

def get_db():
    return psycopg2.connect(os.environ["DATABASE_URL"])

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            key TEXT PRIMARY KEY,
            ciphertext BYTEA NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.route("/")
def index():
    return jsonify({"endpoints": ["/", "/notes", "/notes/<key>"]})

@app.route("/notes")
def list_keys():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT key FROM notes")
    keys = [row[0] for row in cur.fetchall()]
    conn.close()
    return jsonify({"keys": keys})

@app.route("/notes/<key>", methods=["GET"])
def get_note(key):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT ciphertext FROM notes WHERE key = %s", (key,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    plaintext = box.decrypt(bytes(row[0]))
    return jsonify({"key": key, "content": plaintext.decode()})

@app.route("/notes/<key>", methods=["POST"])
def set_note(key):
    data = request.get_json()
    content = data.get("content", "")
    ciphertext = box.encrypt(content.encode())
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO notes (key, ciphertext) VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET ciphertext = EXCLUDED.ciphertext
    """, (key, ciphertext))
    conn.commit()
    conn.close()
    return jsonify({"key": key, "stored": True, "ciphertext_len": len(ciphertext)})

@app.route("/notes/<key>", methods=["DELETE"])
def delete_note(key):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM notes WHERE key = %s", (key,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return jsonify({"key": key, "deleted": deleted})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
