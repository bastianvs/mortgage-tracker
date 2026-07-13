"""Bank of America mortgage rate scraper.

Uses r.jina.ai as a rendering proxy to bypass client-side JS rendering.
Scrapes both the standard refinance page and the jumbo loan page.
"""

import re
import subprocess
import json


def _fetch_via_jina(url: str) -> str:
    """Fetch a URL through the Jina reader proxy."""
    jina_url = f"https://r.jina.ai/{url}"
    result = subprocess.run(
        ["curl", "-sL", "--max-time", "25", jina_url],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl exited {result.returncode}")
    text = result.stdout
    if not text or len(text) < 200:
        raise RuntimeError(f"Jina returned too little content ({len(text) if text else 0} chars)")
    return text


def _parse_rate_table(text: str, source_label: str) -> tuple:
    """
    Parse BOFA rate tables from Jina markdown output.
    Returns (fixed_entries, arm_entries).
    """
    fixed_entries = []
    arm_entries = []

    # Pattern: | 30-year fixed | Rate X.XXX% | APR Y.YYY% | Points Z.ZZZ | ...
    # or       | 30-year fixed Rate Mortgage | Rate X.XXX% | APR Y.YYY% | ...
    # or       | 5y/6m ARM variable | Rate X.XXX% | APR Y.YYY% | ...

    rate_pattern = re.compile(
        r"\|\s*(.+?)\s*\|\s*Rate\s+(\d+\.\d{2,4})%\s*\|\s*APR\s+(\d+\.\d{2,4})%"
    )

    for match in rate_pattern.finditer(text):
        product_name = match.group(1).strip()
        rate = float(match.group(2))
        apr = float(match.group(3))

        product_lower = product_name.lower()

        # Skip products that aren't mortgage rates
        if "home equity" in product_lower or "heloc" in product_lower:
            continue

        # Determine if it's an ARM
        is_arm = "arm" in product_lower or "adjustable" in product_lower

        # Extract term
        term = ""

        # ARM patterns: "5y/6m ARM", "7y/6m ARM", "10y/6m ARM"
        arm_match = re.search(r"(\d+)y/6m\s+ARM", product_name, re.IGNORECASE)
        if arm_match:
            years = arm_match.group(1)
            if years == "5":
                term = "5/1 ARM"
            elif years == "7":
                term = "7/1 ARM"
            elif years == "10":
                term = "10/1 ARM"
            else:
                term = f"{years}/1 ARM"
            is_arm = True
        elif "variable" in product_lower:
            # "5y/6m ARM variable" → already handled above
            # "ARM variable" without years
            arm_match2 = re.search(r"(\d+)y", product_name, re.IGNORECASE)
            if arm_match2:
                years = arm_match2.group(1)
                if years == "5":
                    term = "5/1 ARM"
                elif years == "7":
                    term = "7/1 ARM"
                elif years == "10":
                    term = "10/1 ARM"
                else:
                    term = f"{years}/1 ARM"
                is_arm = True

        # Fixed patterns: "30-year fixed", "30-year fixed Rate Mortgage", "15-year fixed", etc.
        if not is_arm:
            fixed_match = re.search(r"(\d+)-year\s+fixed", product_name, re.IGNORECASE)
            if fixed_match:
                years = fixed_match.group(1)
                term = f"{years}-Year Fixed"

        if not term:
            continue

        # Add jumbo suffix if it's from the jumbo page
        if "jumbo" in source_label.lower():
            term += " Jumbo"

        entry = {"term": term, "rate": rate, "apr": apr}
        dedup_key = (term, rate)

        if is_arm:
            if dedup_key not in {(e["term"], e["rate"]) for e in arm_entries}:
                arm_entries.append(entry)
        else:
            if dedup_key not in {(e["term"], e["rate"]) for e in fixed_entries}:
                fixed_entries.append(entry)

    return fixed_entries, arm_entries


def scrape(fetch_html):
    """
    Fetch BOFA mortgage rates from refinance and jumbo pages.
    """
    refinance_url = "https://www.bankofamerica.com/mortgage/refinance-rates/"
    jumbo_url = "https://www.bankofamerica.com/mortgage/jumbo-loans/"

    all_fixed = []
    all_arm = []

    # Get refinance page rates (conforming)
    try:
        text = _fetch_via_jina(refinance_url)
        fixed, arm = _parse_rate_table(text, "Conforming")
        all_fixed.extend(fixed)
        all_arm.extend(arm)
    except Exception as e:
        print(f"  ⚠ BOFA refinance page failed: {e}")

    # Get jumbo page rates
    try:
        text = _fetch_via_jina(jumbo_url)
        fixed, arm = _parse_rate_table(text, "Jumbo")
        all_fixed.extend(fixed)
        all_arm.extend(arm)
    except Exception as e:
        print(f"  ⚠ BOFA jumbo page failed: {e}")

    # Sort by rate ascending
    all_fixed.sort(key=lambda x: x["rate"])
    all_arm.sort(key=lambda x: x["rate"])

    result = {
        "name": "Bank of America",
        "url": refinance_url,
        "fixed": all_fixed,
        "arm": all_arm,
    }

    return result


if __name__ == "__main__":
    def fetch_html(url):
        import httpx
        r = httpx.get(url, timeout=25, follow_redirects=True)
        r.raise_for_status()
        return r.text

    result = scrape(fetch_html)
    print(json.dumps(result, indent=2))