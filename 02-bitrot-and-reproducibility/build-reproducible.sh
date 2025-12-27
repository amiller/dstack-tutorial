#!/usr/bin/env bash
set -euo pipefail

# Reproducible build script for TEE Oracle
# Tests that the build produces identical output across runs

cd "$(dirname "$0")"

for cmd in docker skopeo jq; do
    command -v "$cmd" >/dev/null || { echo "Required: $cmd"; exit 1; }
done

echo "=== Building TEE Oracle (reproducible) ==="

# Ensure buildx builder exists
if ! docker buildx inspect repro-builder &>/dev/null; then
    docker buildx create --name repro-builder --driver docker-container
fi

build_image() {
    local output_file="$1"
    docker buildx build \
        --builder repro-builder \
        --build-arg SOURCE_DATE_EPOCH=0 \
        --no-cache \
        --output type=oci,dest="$output_file",rewrite-timestamp=true \
        .
}

# Build 1
echo ""
echo "Build 1..."
build_image build1.tar
HASH1=$(sha256sum build1.tar | awk '{print $1}')
echo "  Hash: ${HASH1:0:16}..."

# Build 2
echo ""
echo "Build 2..."
build_image build2.tar
HASH2=$(sha256sum build2.tar | awk '{print $1}')
echo "  Hash: ${HASH2:0:16}..."

# Compare
echo ""
echo "=== Results ==="
if [[ "$HASH1" == "$HASH2" ]]; then
    echo "REPRODUCIBLE - both builds identical"
    echo ""
    echo "Image digest:"
    skopeo inspect oci-archive:build1.tar | jq -r .Digest

    # Save manifest for future verification
    cat > build-manifest.json << EOF
{
  "image_hash": "$HASH1",
  "image_digest": "$(skopeo inspect oci-archive:build1.tar | jq -r .Digest)",
  "build_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "source_date_epoch": 0
}
EOF
    echo ""
    echo "Saved: build-manifest.json"

    # Load into docker for local testing
    docker load < build1.tar 2>/dev/null || true

    rm -f build1.tar build2.tar
    exit 0
else
    echo "NOT REPRODUCIBLE - builds differ"
    echo ""
    echo "Build 1: $HASH1"
    echo "Build 2: $HASH2"
    echo ""
    echo "Debug: keeping build1.tar and build2.tar for inspection"
    echo "Compare with: diff <(tar -tvf build1.tar) <(tar -tvf build2.tar)"
    exit 1
fi
