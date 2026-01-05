# Writing Improvement Notes for Section 01

Based on student feedback (James, Nerla) and follow-up discussion.

---

## Bug Reports (Nerla)

1. **TLS fingerprint blank on second request** — Fixed: added `{ agent: false }` to disable connection keep-alive. Without this, socket reuse means `getPeerCertificate()` returns empty on subsequent requests.

2. **Docker build example needed --no-cache** — The example showing two builds give different hashes didn't work initially (both gave same value). Fixed: added `--no-cache` to the commands.

---

## Issues to Address

### 1. Not Active Enough
- No hands-on component requiring code changes
- User can follow tutorial without opening source code
- **Fix:** Add exercise (e.g., modify oracle to fetch ETH instead of BTC, or scavenger hunt through logs)

### 2. Too Verbose / "AI Slop"
- Smart Contract Analogy section has 4 bullets — collapse to 1-2 sentences
- "How Auditing Works" section is philosophical but unclear
- **Fix:** Tighten prose, lead with concrete examples

### 3. Behavioral Gap Section Confusing
- "attestation proves production runs *something*" — too vague
- James: "Why would an auditor's conclusion not be on code they read which they understand is what is running?"
- **Fix:** Rewrite with concrete threat model (see below)

### 4. Broken Link
- Line 87: `reproducibility docs` link is TODO placeholder
- **Fix:** Link to real docs or remove

---

## Rewrite Notes: The Auditor Perspective

### Core Insight
Reproducibility is *means to an end* — the end is auditability.

### What Auditors Actually Do (range of activities)
- Run docker compose in simulator
- Change env vars, API endpoints, test different inputs
- Test pieces independently, create test harnesses
- (Advanced) formal methods, static analysis
- For dstack specifically, minimum bar:
  1. Can auditor **build** the container?
  2. Can auditor **run** the container?

### Even When Hashes Match, Differences Remain
- Environment variables: auditor won't have production secrets, must populate their own
- Attestation checks: production verifies real attestations, auditor runs in simulator
- Auditor essentially runs in "debug mode" — bypassing attestation checks or using mock attestation
- The hash match proves *code* is identical, but *runtime context* differs
- Auditor must reason: "would this code behave differently with real secrets / real attestation?"

### When Reproducibility Fails
- Auditor can still inspect diffs (section 02 has layer-by-layer workflow)
- Many diffs are benign: timestamps, compiler metadata, cache paths
- Auditor judges: "can I explain this diff? is it benign?"
- If yes → audit proceeds (higher cost)
- If no → audit fails / deeper investigation

### Threat Model to Name Explicitly
- **Adversary:** Developer with obfuscated malicious code
- **Attack:** Code detects "am I on testbench?" and behaves differently
  - Check for simulator socket vs real TDX
  - Check for specific env vars only present in production
  - Time-delayed activation ("works fine for first 30 days")
- **Defense:** Reproducibility means auditor's local build == production code
- If hashes match → no room for code-level divergent behavior
- Runtime divergence (env vars, attestation) must be reasoned about separately

### Economic Framing
- Same quality of scrutiny, less auditor work = cheaper audit
- Hash match = instant verification (cheapest)
- Explainable diff = manual review (more expensive)
- Unexplainable diff = audit fails (most expensive outcome for developer)

---

## Rewrite Notes: Smart Contract Analogy

Collapse to 2 sentences max:

> Smart contracts solved this: open source code, on-chain codehash, reproducible compilation, anyone can verify. TEE apps need the same pattern — the attestation is the codehash, but without reproducible builds there's no way to connect it to auditable source.

---

## Hands-On Exercise Ideas

**APPLIED** — See README.md "Exercises" section. Added:
1. Find report_data binding (scavenger hunt)
2. Change BTC to ETH (code change → hash change)
3. **Audit a public app** — NEW: `verify_public_app.py` fetches attestation from cloud API and app_compose from 8090 endpoint
4. Env var and compose-hash boundary (runtime config not measured)

**Key discovery:** Public apps expose `app_compose` via the tappd info page at `https://{app_id}-8090.{gateway}/`. Combined with attestation from `https://cloud-api.phala.network/api/v1/apps/{app_id}/attestations`, anyone can audit any public app without authentication.

---

## Suggested New Section Order

1. What it does (diagram) — keep
2. Run Locally — keep
3. Endpoints — keep
4. **Hands-on exercise** — NEW (before verification)
5. Verification — keep but tighten
6. Critical Thinking: Auditor's Perspective — REWRITE per above
7. Next Steps — keep
