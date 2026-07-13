"""US Bank mortgage rate scraper (via Jina reader).

USB renders rates dynamically per term. We fetch several specific pages.
"""

import re
import subprocess
import json


def _fetch(url: str) -> str:
    jina_url = f"https://r.jina.ai/{url}"
    result = subprocess.run(
        ["curl", "-sL", "--max-time", "20", jina_url],
        capture_output=True, text=True, timeout=25,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl exited {result.returncode}")
    text = result.stdout
    if not text or len(text) < 200:
        raise RuntimeError(f"USB: Jina returned {len(text) if text else 0} chars")
    return text


def _find_rate_apr(text: str):
    """Find first Rate/APR pair in text like '6.625%Rate' '6.797%APR'."""
    rate_m = re.search(r"(\d+\.\d{2,4})%\s*Rate", text)
    apr_m = re.search(r"(\d+\.\d{2,4})%\s*APR", text)
    if rate_m:
        rate = float(rate_m.group(1))
        apr = float(apr_m.group(1)) if apr_m else None
        return rate, apr
    return None, None


def scrape(fetch_html):
    base = "https://www.usbank.com/home-loans/refinance"
    state = "state=CA"

    fixed_entries = []
    arm_entries = []

    # 30-Year Fixed
    try:
        text = _fetch(f"{base}/conventional-fixed-rate-refinance/30-year-fixed-refinance-rates.html?{state}")
        r, a = _find_rate_apr(text)
        if r:
            fixed_entries.append({"term": "30-Year Fixed", "rate": r, "apr": a})
    except Exception as e:
        print(f"  ⚠ USB 30yr: {e}")

    # 15-Year Fixed
    try:
        text = _fetch(f"{base}/conventional-fixed-rate-refinance/15-year-fixed-refinance-rates.html?{state}")
        r, a = _find_rate_apr(text)
        if r:
            fixed_entries.append({"term": "15-Year Fixed", "rate": r, "apr": a})
    except Exception as e:
        print(f"  ⚠ USB 15yr: {e}")

    # Mortgage rates page for ARM/Jumbo
    try:
        text = _fetch(f"https://www.usbank.com/home-loans/mortgage/mortgage-rates.html?{state}")
        # 30-Year from mortgage page (different than refinance)
        r, a = _find_rate_apr(text)
        # ARM rates appear after "Adjustable-rate" text; look for second rate
        rates = re.findall(r"(\d+\.\d{2,4})%\s*Rate", text)
        aprs = re.findall(r"(\d+\.\d{2,4})%\s*APR", text)
        if len(rates) >= 2 and len(aprs) >= 2:
            # First pair is fixed, second pair is likely ARM
            arm_entries.append({"term": "7/1 ARM", "rate": float(rates[1]), "apr": float(aprs[1])})
    except Exception as e:
        print(f"  ⚠ USB mortgage page: {e}")

    fixed_entries.sort(key=lambda x: x["rate"])
    arm_entries.sort(key=lambda x: x["rate"])

    return {
        "name": "U.S. Bank",
        "url": f"{base}/refinance-rates.html?{state}",
        "fixed": fixed_entries,
        "arm": arm_entries,
    }


if __name__ == "__main__":
    result = scrape(None)
    print(json.dumps(result, indent=2))