# Tutorial 02: Bitrot and Reproducibility

Make your TEE app verifiable by auditors—now and in the future.

This tutorial covers:
- Why reproducibility matters for TEE auditability
- Mechanics of deterministic Docker builds
- Testing reproducibility locally and remotely
- Protecting against bitrot

**Prerequisite:** Read [01-attestation-and-reference-values](../01-attestation-and-reference-values) first to understand the auditor's perspective.

---

## The Developer's Challenge

In [01-attestation-and-reference-values](../01-attestation-and-reference-values), we saw what auditors demand:

1. Source code
2. Build instructions
3. Reference hash
4. **Proof that rebuilding produces the reference hash**

Item #4 is your job as a developer. If an auditor can't rebuild your image and get the same hash, they can't verify your deployment. Your app fails the audit before they even read the code.

But there's a second threat: **bitrot**.

### The Bitrot Problem

Even with perfect reproducibility today, builds can break over time:

- **snapshot.debian.org** doesn't guarantee permanence
- **npm packages** get unpublished (left-pad incident)
- **Docker Hub** prunes old images
- **GitHub releases** can be deleted

In 2 years, your reproducible build might fail because dependencies vanished. The attestation becomes unverifiable—an auditor can't rebuild to confirm the hash.

**The consequence:** Your "auditable" app degrades back to "trust me."

---

## Quick Start

```bash
# Build and verify reproducibility
./build-reproducible.sh

# Test on a remote machine
./verify-remote.sh user@other-host
```

If both succeed, you have a reproducible build.

---

## What Makes Builds Non-Reproducible

Docker builds are **not reproducible by default**:

```bash
$ docker build -t test:v1 .
$ docker build -t test:v2 .
$ docker inspect test:v1 --format='{{.Id}}'
sha256:a1b2c3...
$ docker inspect test:v2 --format='{{.Id}}'
sha256:d4e5f6...   # Different!
```

Sources of non-determinism:

| Source | Why It Breaks Builds |
|--------|---------------------|
| Image tags | `node:22` points to different images over time |
| Package versions | `apt-get install curl` gets latest version |
| Timestamps | Files have build-time timestamps |
| Caches | npm/pip/apt leave timestamped cache files |
| Layer ordering | BuildKit may reorder layers |

---

## Making Builds Reproducible

### 1. Pin Base Images by Digest

```dockerfile
# BAD: Tag can change
FROM node:22-slim

# GOOD: Pinned to exact image
FROM node:22-slim@sha256:773413f36941ce1e4baf74b4a6110c03dcc4f968daffc389d4caef3f01412d2a
```

Get the digest:
```bash
docker pull node:22-slim
docker inspect node:22-slim --format='{{index .RepoDigests 0}}'
```

### 2. Pin Package Versions

```dockerfile
# BAD: Version depends on build date
RUN apt-get update && apt-get install -y curl

# GOOD: Use Debian snapshot for point-in-time reproducibility
RUN echo 'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/20250101T000000Z bookworm main' \
    > /etc/apt/sources.list && \
    apt-get -o Acquire::Check-Valid-Until=false update && \
    apt-get install -y curl=7.88.1-10+deb12u8
```

For npm, use `package-lock.json` with exact versions (no `^` or `~`).

### 3. Normalize Timestamps

```dockerfile
ARG SOURCE_DATE_EPOCH=0
RUN find /app -exec touch -d "@${SOURCE_DATE_EPOCH}" {} +
```

### 4. Clean All Caches

```dockerfile
RUN npm ci --omit=dev --ignore-scripts && \
    rm -rf /tmp/npm-cache /tmp/node-compile-cache && \
    rm -rf /var/lib/apt/lists/* /var/log/* /var/cache/ldconfig/aux-cache
```

### 5. Use BuildKit with rewrite-timestamp

```bash
docker buildx build \
  --build-arg SOURCE_DATE_EPOCH=0 \
  --output type=oci,dest=./image.tar,rewrite-timestamp=true \
  .
```

---

## The Complete Example

This directory contains a reproducible version of the oracle from 01-attestation.

**Dockerfile:**
```dockerfile
ARG SOURCE_DATE_EPOCH=0

FROM node:22-slim@sha256:773413f36941ce1e4baf74b4a6110c03dcc4f968daffc389d4caef3f01412d2a

ARG SOURCE_DATE_EPOCH
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV npm_config_cache=/tmp/npm-cache

WORKDIR /app

# --chmod=644 normalizes permissions across environments (local vs CI)
COPY --chmod=644 package.json package-lock.json ./

RUN npm ci --omit=dev --ignore-scripts && \
    rm -rf /tmp/npm-cache /tmp/node-compile-cache && \
    find /app -exec touch -d "@${SOURCE_DATE_EPOCH}" {} + 2>/dev/null || true

COPY --chmod=644 app.mjs ./
RUN touch -d "@${SOURCE_DATE_EPOCH}" /app/app.mjs

CMD ["node", "app.mjs"]
```

**Build and verify:**
```bash
./build-reproducible.sh
```

Output:
```
=== Building TEE Oracle (reproducible) ===

Build 1...
  Hash: 5864fb1fdf1ee22b...

Build 2...
  Hash: 5864fb1fdf1ee22b...

=== Results ===
REPRODUCIBLE - both builds identical

Image digest:
sha256:afadb40549b91ca4f9031e8ecd79bd4095b68afadbf6578fbecc57d0f6dfeab2

Saved: build-manifest.json
```

---

## Testing Reproducibility

### Method 1: Double-build Locally

The build script does this automatically—builds twice with `--no-cache`, compares hashes.

### Method 2: Remote Machine

Same source, different environment:

```bash
./verify-remote.sh user@other-machine
```

This catches:
- Architecture-specific issues
- Toolchain differences
- Environment variable leakage

### Method 3: GitHub Actions

The gold standard—CI builds and compares against committed hash:

```yaml
# .github/workflows/verify-reproducible.yml
name: Verify Reproducible Build
on: [push, pull_request]
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build and verify
        run: |
          ./build-reproducible.sh
          EXPECTED=$(jq -r .image_hash build-manifest.json.committed)
          ACTUAL=$(jq -r .image_hash build-manifest.json)
          [[ "$EXPECTED" == "$ACTUAL" ]] || exit 1
```

---

## Debugging Non-Reproducible Builds

When builds don't match, you need to find what differs. Here's the workflow:

### Step 1: Compare Layer Hashes

```bash
# Extract both images
mkdir -p /tmp/img1 /tmp/img2
tar -xf build1.tar -C /tmp/img1
tar -xf build2.tar -C /tmp/img2

# Get layer lists from manifests
cat /tmp/img1/index.json | jq -r '.manifests[0].digest' | cut -d: -f2 | \
  xargs -I{} cat /tmp/img1/blobs/sha256/{} | jq '.layers[].digest'
```

### Step 2: Find Differing Layers

```bash
# Compare layer hashes - identical base image layers will match
comm -3 <(ls /tmp/img1/blobs/sha256/ | sort) <(ls /tmp/img2/blobs/sha256/ | sort)
```

### Step 3: Extract and Diff Layer Contents

```bash
# Extract a differing layer
mkdir -p /tmp/layer1 /tmp/layer2
tar -xf /tmp/img1/blobs/sha256/<hash1> -C /tmp/layer1
tar -xf /tmp/img2/blobs/sha256/<hash2> -C /tmp/layer2

# Compare
diff -r /tmp/layer1 /tmp/layer2
```

### Step 4: Check Tar Metadata

Often the file contents are identical but tar metadata differs:

```bash
tar -tvf /tmp/img1/blobs/sha256/<hash1> | head
tar -tvf /tmp/img2/blobs/sha256/<hash2> | head
```

Look for differences in:
- **File permissions** (`-rw-r--r--` vs `-rw-rw-r--`)
- **Ownership** (uid/gid)
- **Timestamps** (should be 1970-01-01 if normalized)

### Common CI vs Local Divergence

| Issue | Cause | Fix |
|-------|-------|-----|
| **File permissions** | Local files have different perms than CI checkout | `COPY --chmod=644` |
| **Buildx version** | Different `rewrite-timestamp` behavior | Pin buildx version or update both |
| **Index.json structure** | Buildx versions add different metadata | Usually harmless if layer hashes match |

### File Permissions: The Most Common Issue

Git doesn't preserve all file permissions. Your local files might be `664` while CI checkout is `644`:

```dockerfile
# BAD: Copies source file permissions (varies by environment)
COPY package.json ./

# GOOD: Normalizes permissions
COPY --chmod=644 package.json ./
```

---

## Known Issues

Some packages break reproducibility:

| Package | Issue | Workaround |
|---------|-------|------------|
| Node.js 22+ | Compile cache in `/tmp/node-compile-cache` | `rm -rf /tmp/node-compile-cache` |
| Python pip | Timestamps in `.pyc` files | `PYTHONDONTWRITEBYTECODE=1` |
| Go binaries | Embeds build paths | Use `-trimpath` flag |
| npm native deps | Compilation varies | Pin compiler or use prebuilt |

---

## Protecting Against Bitrot

For long-term auditability, vendor your dependencies:

```bash
# Download APT packages
mkdir -p vendor/apt && cd vendor/apt
apt-get download curl=7.88.1-10+deb12u8

# Download npm packages
mkdir -p vendor/npm && cd vendor/npm
npm pack express@4.18.2

# Save base image
docker save node:22-slim@sha256:773413... > vendor/images/node-22-slim.tar
```

Then build offline:
```bash
OFFLINE=1 ./build-reproducible.sh
```

This is extra work. Use it for:
- Apps handling significant value
- Deployments that need auditability for years
- Regulated environments

---

## Levels of Reproducibility

| Level | Achieves | Effort | When to Use |
|-------|----------|--------|-------------|
| **None** | "Runs in TEE" | Minimal | Demos only |
| **Loose** | Same hash today | Moderate | Most production apps |
| **Strict** | Rebuildable in 2+ years | High | High-stakes apps |
| **Extreme** | Bit-for-bit on any machine | Very high | Critical infrastructure |

Start with **Loose**. Move to **Strict** if auditability must survive time.

---

## Critical Thinking: Developer Self-Assessment

Before claiming your app is auditable:

1. **Can someone else rebuild and get the same hash?**
   - Run `./verify-remote.sh` on a different machine

2. **Are all dependencies pinned?**
   - Check for `^` or `~` in package.json
   - Check for unpinned apt packages

3. **Is your build documented and automated?**
   - Can a new team member reproduce it?

4. **Will it still work in 2 years?**
   - Consider vendoring if yes matters

---

## Next Steps

- [03-keys-and-replication](../03-keys-and-replication): Derive persistent keys
- [04-gateways-and-tls](../04-gateways-and-tls): Custom domains and TLS
- For Nix-based reproducible builds, see the [reproducible-builds-playground](../../refs/reproducible-builds-playground)

## Files

```
02-bitrot-and-reproducibility/
├── docker-compose.yaml     # Reproducible compose
├── Dockerfile              # Pinned base, lockfile, cache cleanup
├── package.json            # Pinned @phala/dstack-sdk
├── package-lock.json       # Exact dependency versions
├── app.mjs                 # Oracle application
├── build-reproducible.sh   # Build + verify script
├── verify-remote.sh        # Remote machine verification
└── README.md
```
