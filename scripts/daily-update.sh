#!/usr/bin/env bash
set -euo pipefail

# === Mortgage Rate Daily Update ===
# Fetches rates (Python), builds history, pushes to GitHub Pages

TRACKER_DIR="/home/node/.openclaw/workspace/mortgage-tracker"
export GIT_SSH_COMMAND="ssh -i /home/node/.ssh/id_ed25519_bastianvs -o IdentitiesOnly=yes"

# Supabase — for historical rate tracking
export SUPABASE_URL="https://ozeeqcefpwcfhmhstmon.supabase.co"
export SUPABASE_SERVICE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im96ZWVxY2VmcHdjZmhtaHN0bW9uIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4Mzc5Mzk3NywiZXhwIjoyMDk5MzY5OTc3fQ.LGm71nWqOxxf9ZbwL5UUNmHecz8Oj58YcKuhvLhixU8"

cd "$TRACKER_DIR"

echo "=== Mortgage Rate Daily Update — $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# 1. Fetch latest rates
echo "→ Fetching rates..."
python3 fetch_rates.py

# 2. Build history.json for charts
echo "→ Building history..."
python3 build_history.py

# 3. Commit to master
echo "→ Committing to master..."
git add -A
git diff --staged --quiet || git commit -m "Daily rate update — $(date -u +%Y-%m-%d)"
git push origin master

# 4. Deploy to gh-pages (orphan branch approach to keep it clean)
echo "→ Deploying to GitHub Pages..."
TMP=$(mktemp -d)
cp site/data/latest.json "$TMP/"
cp site/data/history.json "$TMP/"
cp site/index.html "$TMP/"

git branch -D gh-pages 2>/dev/null || true
git checkout --orphan gh-pages
git rm -rf . 2>/dev/null || true

# Also nuke gitignored files that shouldn't be on gh-pages
rm -rf data/rates-*.json scrapers scripts node_modules __pycache__ 2>/dev/null || true

mkdir -p data
cp "$TMP/latest.json" data/
cp "$TMP/history.json" data/
cp "$TMP/index.html" .
echo "rates.bastian.services" > CNAME
touch .nojekyll
rm -rf "$TMP"

git add -A
git commit -m "deploy $(date -u +%Y-%m-%d)"
git push origin gh-pages --force
git checkout master

echo "=== Done ==="