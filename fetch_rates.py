#!/usr/bin/env python3
"""
Mortgage Rate Fetcher v4 — Direct lender sources
No Bankrate dependency.

Sources:
  Credit Unions: PatelCo, Star One, Provident, Golden 1, First Tech
  Banks: Bank of America, Wells Fargo, Chase

Output:
  data/rates-YYYY-MM-DD.json
  site/data/latest.json
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
    "currentRate": 5.8,
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
    """Fetch page HTML with httpx."""
    client = get_client()
    r = client.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text


def run_all_scrapers():
    """Run all scrapers and collect results."""
    from scrapers.patelco import scrape as sc_patelco
    from scrapers.starone import scrape as sc_starone
    from scrapers.wellsfargo import scrape as sc_wf
    from scrapers.pmms import scrape as sc_pmms

    scrapers = [
        ("patelco", sc_patelco),
        ("starone", sc_starone),
        ("wellsfargo", sc_wf),
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


def build_summary(institutions: dict) -> dict:
    """Build summary from all institution data."""
    all_fixed_30 = []
    all_fixed_15 = []
    all_arm_5_1 = []
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
            elif "10/1" in term:
                all_arm_10_1.append(a["rate"])

    # PMMS national averages
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
        "10_1_arm_avg": avg(all_arm_10_1),
        "national_30_year_fixed": pmms_rates.get("30_year_fixed"),
        "national_15_year_fixed": pmms_rates.get("15_year_fixed"),
        "my_rate": MY_PROFILE["currentRate"],
        "my_loan_type": MY_PROFILE["loanType"],
        "institutions_count": len(institutions),
    }

    # Backward-compatible aliases for website
    summary["30_year_fixed"] = summary["30_year_fixed_avg"] or pmms_rates.get("30_year_fixed")
    summary["15_year_fixed"] = summary["15_year_fixed_avg"] or pmms_rates.get("15_year_fixed")
    summary["5_1_arm"] = summary["5_1_arm_avg"]
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

    # Save files
    day_file = DATA_DIR / f"rates-{today}.json"
    day_file.write_text(json.dumps(result, indent=2))
    print(f"\nSaved: {day_file}")

    latest_file = SITE_DATA_DIR / "latest.json"
    latest_file.write_text(json.dumps(result, indent=2))
    print(f"Saved: {latest_file}")

    # Print dashboard
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
