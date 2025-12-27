#!/usr/bin/env bash
set -euo pipefail

# Verify reproducibility on a remote machine
# Usage: ./verify-remote.sh user@host [expected-hash]

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 user@host [expected-hash]"
    echo ""
    echo "Tests if the build reproduces on a different machine."
    echo "If expected-hash is provided, compares against it."
    echo "Otherwise, uses hash from local build-manifest.json."
    exit 1
fi

REMOTE="$1"
cd "$(dirname "$0")"

if [[ $# -ge 2 ]]; then
    EXPECTED="$2"
elif [[ -f build-manifest.json ]]; then
    EXPECTED=$(jq -r .image_hash build-manifest.json)
else
    echo "No expected hash provided and no build-manifest.json found."
    echo "Run ./build-reproducible.sh first, or provide hash as argument."
    exit 1
fi

echo "=== Remote Reproducibility Test ==="
echo "Remote: $REMOTE"
echo "Expected hash: ${EXPECTED:0:16}..."
echo ""

# Create tarball of source files
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

tar -czf "$TMPDIR/src.tar.gz" \
    Dockerfile \
    package.json \
    package-lock.json \
    app.mjs \
    build-reproducible.sh

echo "Copying source to remote..."
scp "$TMPDIR/src.tar.gz" "$REMOTE:/tmp/tee-oracle-verify.tar.gz"

echo "Building on remote..."
REMOTE_HASH=$(ssh "$REMOTE" bash -s << 'ENDSSH'
set -e
cd /tmp
rm -rf tee-oracle-verify
mkdir tee-oracle-verify
cd tee-oracle-verify
tar -xzf ../tee-oracle-verify.tar.gz

# Ensure buildx (suppress all output)
docker buildx create --name repro-builder --driver docker-container >/dev/null 2>&1 || true

docker buildx build \
    --builder repro-builder \
    --build-arg SOURCE_DATE_EPOCH=0 \
    --no-cache \
    --output type=oci,dest=verify.tar,rewrite-timestamp=true \
    . >/dev/null 2>&1

sha256sum verify.tar | awk '{print $1}'
rm -rf /tmp/tee-oracle-verify*
ENDSSH
)

echo ""
echo "=== Results ==="
echo "Expected: $EXPECTED"
echo "Remote:   $REMOTE_HASH"

if [[ "$EXPECTED" == "$REMOTE_HASH" ]]; then
    echo ""
    echo "VERIFIED - remote build matches local"
    exit 0
else
    echo ""
    echo "MISMATCH - remote build differs from local"
    exit 1
fi
