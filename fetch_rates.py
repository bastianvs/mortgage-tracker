#!/usr/bin/env python3
"""
Mortgage Rate Fetcher v4 — Direct lender sources
  Credit Unions: PatelCo, Star One, Golden 1
  Banks: Bank of America, Wells Fargo, Chase
  National: Freddie Mac PMMS

Output:
  data/rates-YYYY-MM-DD.json      — Daily snapshot
  site/data/latest.json            — Latest for website
  Supabase mortgage_rates table    — Historical tracking
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from httpx import Client

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
SITE_DATA_DIR = ROOT / "site" / "data"
SCRAPERS_DIR = ROOT / "scrapers"

DATA_DIR.mkdir(parents=True, exist_ok=True)
SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)

MY_PROFILE = {
    "currentRate": 5.87575757575,
    "loanType": "5/1 ARM",
    "location": "Milpitas, CA 95035",
    "propertyType": "Single-family detached",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# Shared HTTP client with connection pooling
_http_client = None


def get_client():
    global _http_client
    if _http_client is None:
        _http_client = Client(
            headers=HEADERS,
            timeout=12.0,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _http_client


def fetch_html(url: str, timeout: float = 12.0) -> str:
    client = get_client()
    r = client.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text


# ── Supabase upload ──────────────────────────────────────────────


def upload_to_supabase(result: dict) -> bool:
    """Push today's rates to Supabase mortgage_rates table for historical tracking."""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not supabase_url or not supabase_key:
        print("  ⚠ Supabase: SUPABASE_URL/SUPABASE_SERVICE_KEY not set, skipping")
        return False

    institutions = result.get("institutions", {})
    rows = []
    today = result["date"]

    # Pick lowest rate per (lender, term) — the DB unique constraint is on (date, lender, term)
    best = {}
    for _, inst in institutions.items():
        name = inst.get("name", "Unknown")
        for entry in inst.get("fixed", []) + inst.get("arm", []):
            term = entry["term"]
            rate = entry["rate"]
            key = (name, term)
            if key not in best or rate < best[key]["rate"]:
                best[key] = {
                    "date": today,
                    "lender": name,
                    "term": term,
                    "rate": rate,
                    "apr": entry.get("apr"),
                }
    rows = list(best.values())

    if not rows:
        print("  ⚠ Supabase: no rows to upload")
        return False

    # Upsert in batches of 50
    import urllib.request
    import ssl

    ctx = ssl.create_default_context()
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

    success_count = 0
    batch_size = 50
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        data = json.dumps(batch).encode("utf-8")
        # Upsert: POST + on_conflict query param tells PG which columns form the conflict target
        req = urllib.request.Request(
            f"{supabase_url}/rest/v1/mortgage_rates?on_conflict=date,lender,term",
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                status = resp.status
                if status in (200, 201):
                    success_count += len(batch)
                else:
                    print(f"  ⚠ Supabase batch {i//batch_size}: HTTP {status}")
        except Exception as e:
            print(f"  ⚠ Supabase batch {i//batch_size} failed: {e}")

    print(f"  ✓ Uploaded {success_count}/{len(rows)} rate rows to Supabase")
    return True


# ── Scrapers ──────────────────────────────────────────────────────


def run_all_scrapers():
    from scrapers.patelco import scrape as sc_patelco
    from scrapers.starone import scrape as sc_starone
    from scrapers.wellsfargo import scrape as sc_wf
    from scrapers.golden1 import scrape as sc_golden1
    from scrapers.bofa import scrape as sc_bofa
    from scrapers.chase import scrape as sc_chase
    from scrapers.citi import scrape as sc_citi
    from scrapers.pmms import scrape as sc_pmms

    scrapers = [
        ("patelco", sc_patelco),
        ("starone", sc_starone),
        ("wellsfargo", sc_wf),
        ("golden1", sc_golden1),
        ("bofa", sc_bofa),
        ("chase", sc_chase),
        ("citi", sc_citi),
    ]

    institutions = {}
    errors = []

    for name, scraper in scrapers:
        try:
            print(f"→ Fetching {name}...")
            result = scraper(fetch_html)
            institutions[name] = result
            fixed_count = len(result.get("fixed", []))
            arm_count = len(result.get("arm", []))
            print(f"  ✓ {result['name']}: {fixed_count} fixed, {arm_count} ARM rates")
        except Exception as e:
            print(f"  ✗ {name} failed: {e}")
            errors.append({"source": name, "error": str(e)})

    # PMMS (national averages)
    print("→ Fetching pmms (Freddie Mac national averages)...")
    try:
        pmms_result = sc_pmms(fetch_html)
        institutions["pmms"] = pmms_result
        print(f"  ✓ PMMS: {pmms_result.get('rates', {})}")
    except Exception as e:
        print(f"  ✗ pmms failed: {e}")
        errors.append({"source": "pmms", "error": str(e)})

    return institutions, errors


# ── Summary ────────────────────────────────────────────────────────


def build_summary(institutions: dict) -> dict:
    all_fixed_30 = []
    all_fixed_15 = []
    all_arm_5_1 = []
    all_arm_7_1 = []
    all_arm_10_1 = []

    for inst in institutions.values():
        for f in inst.get("fixed", []):
            term = f.get("term", "").lower()
            if "30" in term:
                all_fixed_30.append(f["rate"])
            elif "15" in term:
                all_fixed_15.append(f["rate"])
        for a in inst.get("arm", []):
            term = a.get("term", "").lower()
            if "5/1" in term or "5-1" in term:
                all_arm_5_1.append(a["rate"])
            elif "7/1" in term or "7-1" in term or "7/6" in term:
                all_arm_7_1.append(a["rate"])
            elif "10/1" in term:
                all_arm_10_1.append(a["rate"])

    pmms = institutions.get("pmms", {})
    pmms_rates = pmms.get("rates", {})

    def avg(lst):
        return round(sum(lst) / len(lst), 3) if lst else None

    def best(lst):
        return round(min(lst), 3) if lst else None

    summary = {
        "30_year_fixed_avg": avg(all_fixed_30),
        "30_year_fixed_best": best(all_fixed_30),
        "15_year_fixed_avg": avg(all_fixed_15),
        "15_year_fixed_best": best(all_fixed_15),
        "5_1_arm_avg": avg(all_arm_5_1),
        "5_1_arm_best": best(all_arm_5_1),
        "7_1_arm_avg": avg(all_arm_7_1),
        "7_1_arm_best": best(all_arm_7_1),
        "10_1_arm_avg": avg(all_arm_10_1),
        "national_30_year_fixed": pmms_rates.get("30_year_fixed"),
        "national_15_year_fixed": pmms_rates.get("15_year_fixed"),
        "my_rate": MY_PROFILE["currentRate"],
        "my_loan_type": MY_PROFILE["loanType"],
        "institutions_count": len(institutions),
    }

    summary["30_year_fixed"] = summary["30_year_fixed_avg"] or pmms_rates.get("30_year_fixed")
    summary["15_year_fixed"] = summary["15_year_fixed_avg"] or pmms_rates.get("15_year_fixed")
    summary["5_1_arm"] = summary["5_1_arm_avg"]
    summary["7_1_arm"] = summary["7_1_arm_avg"]
    summary["best_7_1_arm"] = summary["7_1_arm_best"]
    summary["10_1_arm"] = summary["10_1_arm_avg"]
    summary["best_30yr_lender_rate"] = summary["30_year_fixed_best"]

    market_arm = summary["5_1_arm_avg"] or pmms_rates.get("30_year_fixed")
    if market_arm:
        diff = round(market_arm - MY_PROFILE["currentRate"], 3)
        if diff > 0.5:
            assessment = "🌟 Your rate is EXCELLENT — well below market"
        elif diff > 0.25:
            assessment = "✅ Your rate is BETTER than market"
        elif diff > 0.05:
            assessment = "🟢 Your rate is slightly better than market"
        elif diff > -0.05:
            assessment = "🟡 Market is about equal to your rate"
        elif diff > -0.25:
            assessment = "🟠 Market is slightly better — watch for refinance"
        else:
            assessment = "🔴 Market is BETTER — consider refinancing"

        summary["vs_my_rate"] = {
            "market_rate": market_arm,
            "my_rate": MY_PROFILE["currentRate"],
            "difference": diff,
            "assessment": assessment,
        }

    return summary


# ── Main ──────────────────────────────────────────────────────────


def main():
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    print(f"[{now.isoformat()}] Fetching mortgage rates for {today}...")

    institutions, errors = run_all_scrapers()
    summary = build_summary(institutions)

    result = {
        "date": today,
        "fetchedAt": now.isoformat(),
        "profile": MY_PROFILE,
        "institutions": institutions,
        "summary": summary,
    }

    if errors:
        result["errors"] = errors

    # Save local files
    day_file = DATA_DIR / f"rates-{today}.json"
    day_file.write_text(json.dumps(result, indent=2))
    print(f"\nSaved: {day_file}")

    latest_file = SITE_DATA_DIR / "latest.json"
    latest_file.write_text(json.dumps(result, indent=2))
    print(f"Saved: {latest_file}")

    # Upload to Supabase for historical tracking
    print("\n→ Uploading to Supabase...")
    upload_to_supabase(result)

    # Dashboard
    print("\n" + "=" * 60)
    print(f"📊 MORTGAGE RATE DASHBOARD — {today}")
    print("=" * 60)

    s = summary
    fmt = lambda v: f"{v:.3f}%" if v else "N/A"
    print(f"30-Year Fixed:  avg={fmt(s['30_year_fixed_avg'])}  best={fmt(s['30_year_fixed_best'])}")
    print(f"15-Year Fixed:  avg={fmt(s['15_year_fixed_avg'])}  best={fmt(s['15_year_fixed_best'])}")
    print(f"5/1 ARM:        avg={fmt(s['5_1_arm_avg'])}  best={fmt(s['5_1_arm_best'])}")
    print("-" * 60)
    print(f"Your Rate (5/1 ARM): {MY_PROFILE['currentRate']}%")
    if "vs_my_rate" in s:
        v = s["vs_my_rate"]
        print(f"Market rate:            {v['market_rate']:.3f}%")
        print(f"Difference:             {v['difference']:+.3f}%")
        print(f"Status:                 {v['assessment']}")

    print(f"\nSources: {len(institutions)} institutions")
    for name, inst in institutions.items():
        fixed = len(inst.get("fixed", []))
        arm = len(inst.get("arm", []))
        print(f"  {inst['name']}: {fixed} fixed, {arm} ARM")

    if errors:
        print(f"\n⚠️ {len(errors)} sources failed:")
        for e in errors:
            print(f"  {e['source']}: {e['error']}")

    print("=" * 60)
    return result


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()