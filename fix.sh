#!/usr/bin/env bash
set -euo pipefail
cd /home/node/.openclaw/workspace/mortgage-tracker
export GIT_SSH_COMMAND="ssh -i /home/node/.ssh/id_ed25519_bastianvs -o IdentitiesOnly=yes"
sed -i 's/"currentRate": 5.8/"currentRate": 5.875/' fetch_rates.py
python3 fetch_rates.py
git add fetch_rates.py
git commit -m "fix rate 5.875"
git push origin master
git branch -D gh-pages 2>/dev/null || true
git checkout --orphan gh-pages
git rm -rf . 2>/dev/null || true
mkdir -p data
cp site/data/latest.json data/
cp site/index.html .
touch .nojekyll
git add -A
git commit -m "deploy site"
git push origin gh-pages --force
git checkout master
echo "DONE"