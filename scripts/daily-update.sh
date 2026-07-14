#!/usr/bin/env bash
set -euo pipefail

# === Mortgage Rate Daily Update ===
# Fetches rates (Python), builds history, pushes to GitHub Pages

TRACKER_DIR="/home/node/.openclaw/workspace/mortgage-tracker"
export GIT_SSH_COMMAND="ssh -i /home/node/.ssh/id_ed25519_bastianvs -o IdentitiesOnly=yes"

# Supabase — for historical rate tracking
if [ -f "$TRACKER_DIR/.env" ]; then
  set -a; source "$TRACKER_DIR/.env"; set +a
fi
export SUPABASE_URL="https://ozeeqcefpwcfhmhstmon.supabase.co"
export SUPABASE_SERVICE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im96ZWVxY2VmcHdjZmhtaHN0bW9uIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4Mzc5Mzk3NywiZXhwIjoyMDk5MzY5OTc3fQ.LGm71nWqOxxf9ZbwL5UUNmHecz8Oj58YcKuhvLhixU8"

cd "$TRACKER_DIR"

echo "=== Mortgage Rate Daily Update — $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# 1. Fetch latest rates, upload to Supabase
echo "→ Fetching rates..."
python3 fetch_rates.py 2>&1

# 2. Build history.json for chart
echo "→ Building history..."
python3 build_history.py 2>&1

# 3. Push updated data to gh-pages branch
echo "→ Deploying to GitHub Pages..."

TMPDIR=$(mktemp -d)
cp site/data/latest.json "$TMPDIR/"
cp site/data/history.json "$TMPDIR/" 2>/dev/null || true
cp site/index.html "$TMPDIR/"

git stash 2>/dev/null || true
git checkout gh-pages 2>&1

# Ensure CNAME exists for custom domain (rates.bastian.services)
echo "rates.bastian.services" > CNAME

# Clean any stray files from bad deploys
git rm -r --ignore-unmatch scrapers site 2>/dev/null || true

mkdir -p data
cp "$TMPDIR/latest.json" data/
cp "$TMPDIR/history.json" data/ 2>/dev/null || true
cp "$TMPDIR/index.html" .

touch .nojekyll
git add -A
if git diff --cached --quiet; then
  echo "No changes to deploy."
else
  git commit -m "Daily rate update — $(date -u +%Y-%m-%d)"
  git push origin gh-pages 2>&1
  echo "✓ Deployed to GitHub Pages"
fi

# Back to master
git checkout master 2>&1
git stash pop 2>/dev/null || true
rm -rf "$TMPDIR"

echo "=== Done ==="