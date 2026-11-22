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

# ── 3. Commit changes to master ─────────────────────────────────
git add -A
git diff --staged --quiet || git commit -m "Daily rate update — $(date +%Y-%m-%d)"
git push origin master

# ── 4. Deploy to gh-pages ───────────────────────────────────────
# Save needed files somewhere safe BEFORE the orphan branch nukes everything
TMP=$(mktemp -d)
cp site/data/latest.json "$TMP/"
cp site/data/history.json "$TMP/"
cp site/index.html "$TMP/"

# Rebuild gh-pages branch cleanly
git branch -D gh-pages 2>/dev/null || true
git checkout --orphan gh-pages

# Remove everything from working tree, but save the tmp files (they're outside repo)
git rm -rf . 2>/dev/null || true

# Now put back only what gh-pages needs
mkdir -p data
cp "$TMP/latest.json" data/
cp "$TMP/history.json" data/
cp "$TMP/index.html" .
echo "rates.bastian.services" > CNAME
touch .nojekyll

rm -rf "$TMP"

git add -A
git commit -m "deploy $(date +%Y-%m-%d)"
git push origin gh-pages --force
git checkout master

echo ""
echo "=============================="
echo "✅ DEPLOY DONE"
echo "=============================="