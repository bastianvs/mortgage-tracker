"""Chase mortgage rate scraper (via Jina reader)."""

import re
import subprocess
import json


def scrape(fetch_html):
    url = "https://www.chase.com/personal/mortgage/refinance-rates"
    jina_url = f"https://r.jina.ai/{url}"

    result = subprocess.run(
        ["curl", "-sL", "--max-time", "25", jina_url],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl exited {result.returncode}")
    text = result.stdout
    if not text or len(text) < 200:
        raise RuntimeError(f"Chase: Jina returned {len(text) if text else 0} chars")

    fixed_entries = []
    arm_entries = []

    lines = text.split("\n")
    current_product = None
    current_rate = None
    current_apr = None

    for line in lines:
        stripped = line.strip()

        # Product headers
        product_match = re.match(r"^##\s+(.+)$", stripped)
        if product_match:
            # Save previous product if complete
            if current_product and current_rate is not None:
                _save_entry(current_product, current_rate, current_apr, fixed_entries, arm_entries)
            current_product = product_match.group(1)
            current_rate = None
            current_apr = None
            continue

        # Interest rate
        rate_match = re.match(r"^(\d+\.\d{2,4})%\s*Interest rate$", stripped)
        if rate_match and current_product:
            current_rate = float(rate_match.group(1))
            continue

        # APR
        apr_match = re.match(r"^(\d+\.\d{2,4})%\s*APR$", stripped)
        if apr_match and current_product:
            current_apr = float(apr_match.group(1))
            continue

        # Discount points after APR means this product is complete
        if stripped.startswith("*   Discount points") and current_product and current_rate is not None:
            pass  # Product complete, save is triggered on next header

    # Save last product
    if current_product and current_rate is not None:
        _save_entry(current_product, current_rate, current_apr, fixed_entries, arm_entries)

    fixed_entries.sort(key=lambda x: x["rate"])
    arm_entries.sort(key=lambda x: x["rate"])

    return {
        "name": "Chase",
        "url": url,
        "fixed": fixed_entries,
        "arm": arm_entries,
    }


def _save_entry(product, rate, apr, fixed_entries, arm_entries):
    """Parse product name and save into appropriate list."""
    p = product.lower()

    # Skip non-mortgage sections
    if any(x in p for x in ["find answers", "your mortgage", "example", "looking for"]):
        return

    is_arm = "arm" in p or "adjustable" in p
    is_jumbo = "jumbo" in p
    is_fha = "fha" in p

    # Build standard term
    if is_arm:
        if "7/6" in p:
            term = "7/1 ARM"
        elif "5/1" in p or "5/6" in p:
            term = "5/1 ARM"
        elif "10/1" in p or "10/6" in p:
            term = "10/1 ARM"
        else:
            term = "ARM"
    else:
        yr_match = re.search(r"(\d+)-year", p)
        if yr_match:
            term = f"{yr_match.group(1)}-Year Fixed"
        else:
            return

    if is_jumbo:
        term += " Jumbo"
    if is_fha and not term.endswith("FHA"):
        term += " FHA"

    entry = {"term": term, "rate": rate, "apr": apr}
    dedup_key = (term, rate)

    if is_arm:
        if dedup_key not in {(e["term"], e["rate"]) for e in arm_entries}:
            arm_entries.append(entry)
    else:
        if dedup_key not in {(e["term"], e["rate"]) for e in fixed_entries}:
            fixed_entries.append(entry)


if __name__ == "__main__":
    def fetch_html(url):
        import httpx
        r = httpx.get(url, timeout=25, follow_redirects=True)
        r.raise_for_status()
        return r.text

    result = scrape(fetch_html)
    print(json.dumps(result, indent=2))