#!/usr/bin/env python3
"""
Build history.json from all daily rate files.
Run after fetch_rates.py to update the website's chart data.
Handles both v3 (old) and v4 (new) summary key formats.
Merges with existing history.json to preserve data across deploys.
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
SITE_DATA_DIR = ROOT / "site" / "data"
SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)

files = sorted(DATA_DIR.glob("rates-*.json"))

history = []
for f in files:
    data = json.loads(f.read_text())
    s = data.get("summary", {})

    # Map old and new keys
    entry = {
        "date": data.get("date", f.stem.replace("rates-", "")),
        "summary": {
            "30_year_fixed": s.get("30_year_fixed_avg") or s.get("30_year_fixed") or s.get("national_30_year_fixed"),
            "15_year_fixed": s.get("15_year_fixed_avg") or s.get("15_year_fixed") or s.get("national_15_year_fixed"),
            "5_1_arm": s.get("5_1_arm_avg") or s.get("5_1_arm"),
            "10_1_arm": s.get("10_1_arm_avg") or s.get("10_1_arm"),
            "best_30yr_lender_rate": s.get("30_year_fixed_best") or s.get("best_30yr_lender_rate"),
            "national_30_year_fixed": s.get("national_30_year_fixed"),
            "national_15_year_fixed": s.get("national_15_year_fixed"),
        },
    }
    history.append(entry)

# If only a few days found (fresh directory), merge with existing history.json
existing_file = SITE_DATA_DIR / "history.json"
if existing_file.exists():
    existing = json.loads(existing_file.read_text())
    # Build set of dates we already have from local data
    new_dates = {e["date"] for e in history}
    # Add existing entries that aren't already covered by local data
    for old_entry in existing:
        if old_entry["date"] not in new_dates:
            history.append(old_entry)

# Sort by date ascending
history.sort(key=lambda e: e["date"])

# Keep last 90 days
trimmed = history[-90:]

out_file = SITE_DATA_DIR / "history.json"
out_file.write_text(json.dumps(trimmed, indent=2))
print(f"History: {len(trimmed)} days written to {out_file}")