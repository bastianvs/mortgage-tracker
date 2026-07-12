#!/usr/bin/env bash
set -euo pipefail

# === Mortgage Rate Daily Update ===
# Called by OpenClaw cron daily
# Fetches rates, builds history, pushes to GitHub Pages, alerts on changes

TRACKER_DIR="/home/node/.openclaw/workspace/mortgage-tracker"
cd "$TRACKER_DIR"

echo "=== Mortgage Rate Daily Update — $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# 1. Fetch latest rates
echo "→ Fetching rates..."
node scripts/fetch-rates.js 2>&1

# 2. Build history.json for chart
echo "→ Building history..."
node scripts/build-history.js 2>&1

# 3. Push updated data to gh-pages branch
echo "→ Deploying to GitHub Pages..."

# Save latest data files to a temp location
TMPDIR=$(mktemp -d)
cp site/data/latest.json "$TMPDIR/"
cp site/data/history.json "$TMPDIR/"

# Switch to gh-pages, update data, push
git stash 2>/dev/null || true
git checkout gh-pages 2>&1

mkdir -p data
cp "$TMPDIR/latest.json" data/
cp "$TMPDIR/history.json" data/

git add data/
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

# 4. Check for rate change alert
ALERT_FILE="$TRACKER_DIR/data/last-change-report.txt"
if [ -f "$ALERT_FILE" ]; then
  echo "ALERT_CHANGE_DETECTED"
  cat "$ALERT_FILE"
fi

echo "=== Done ==="
