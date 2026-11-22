#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/node/.openclaw/workspace/mortgage-tracker"
cd "$REPO_DIR"

export GIT_SSH_COMMAND="ssh -i /home/node/.ssh/id_ed25519_bastianvs -o IdentitiesOnly=yes"

# ── 1. Scrape latest rates ──────────────────────────────────────
echo "→ Running scraper..."
python3 fetch_rates.py

# ── 2. Build chart history ──────────────────────────────────────
echo "→ Building history..."
python3 build_history.py

# ── 3. Commit scraper changes to master ─────────────────────────
git add -A
git diff --staged --quiet || git commit -m "Daily rate update — $(date +%Y-%m-%d)"
git push origin master

# ── 4. Deploy to gh-pages ───────────────────────────────────────
# Copy needed files OUTSIDE the repo FIRST so git rm doesn't eat them
TMP_DEPLOY=$(mktemp -d)
cp site/data/latest.json "$TMP_DEPLOY/latest.json"
cp site/data/history.json "$TMP_DEPLOY/history.json"
cp site/index.html "$TMP_DEPLOY/index.html"

# Rebuild gh-pages branch
git branch -D gh-pages 2>/dev/null || true
git checkout --orphan gh-pages
git rm -rf . 2>/dev/null || true

# Restore deploy files into the root of gh-pages
mkdir -p data
cp "$TMP_DEPLOY/latest.json" data/latest.json
cp "$TMP_DEPLOY/history.json" data/history.json
cp "$TMP_DEPLOY/index.html" index.html
rm -rf "$TMP_DEPLOY"

touch .nojekyll
git add -A
git commit -m "deploy $(date +%Y-%m-%d)"
git push origin gh-pages --force
git checkout master

echo ""
echo "=============================="
echo "✅ DEPLOY DONE"
echo "=============================="