"""Golden 1 Credit Union mortgage rate scraper.

Page is behind Akamai bot protection so we use r.jina.ai as a rendering proxy
which extracts the markdown/text content without needing an API key.

Format from Jina reader:

[Product Name](url)
 Rate Details ... [Jumbo] ...
| Rate | APR | Discount Points |
| --- | --- | --- |
| X.XXX% | Y.YYY% | Z.ZZZ |
"""

import re
import subprocess
import json


def scrape(fetch_html):
    """
    Fetch Golden 1 mortgage rates via r.jina.ai proxy (bypasses Akamai).
    """
    jina_url = "https://r.jina.ai/https://www.golden1.com/credit-cards-loans/home-loans/rates"

    try:
        result = subprocess.run(
            ["curl", "-sL", "--max-time", "25", jina_url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"curl exited {result.returncode}")
        text = result.stdout
    except subprocess.TimeoutExpired:
        raise RuntimeError("Golden1: Jina reader timed out")
    except FileNotFoundError:
        raise RuntimeError("Golden1: curl not available")

    if not text or len(text) < 500:
        raise RuntimeError(f"Golden1: Jina returned too little content ({len(text) if text else 0} chars)")

    fixed_entries = []
    arm_entries = []

    lines = text.split("\n")
    i = 0
    current_section = None  # 'purchase', 'refinance', 'equity'
    in_jumbo = False  # Track whether we're in the Jumbo sub-section
    pending_product = None  # Product name from link text before the table
    pending_is_jumbo = False  # Whether this pending product is Jumbo

    while i < len(lines):
        line = lines[i]

        # Track section headers
        if line.startswith("## Purchase Rates"):
            current_section = "purchase"
            in_jumbo = False
            i += 1
            continue
        elif line.startswith("## Refinance Rates"):
            current_section = "refinance"
            in_jumbo = False
            i += 1
            continue
        elif line.startswith("## Equity Rates") or line.startswith("## Get Your Personalized"):
            current_section = "equity"
            i += 1
            continue

        if current_section != "purchase":
            i += 1
            continue

        # Detect Jumbo sub-section
        stripped = line.strip()
        if "Jumbo Loans!" in stripped:
            in_jumbo = True
            i += 1
            continue

        # Look for link text like [5-Year SOFR ARM](url)
        link_match = re.match(r"\[(.+?)\]\(https?://", stripped)
        if link_match:
            pending_product = link_match.group(1)
            pending_is_jumbo = in_jumbo
            i += 1
            continue

        # Check the "Rate Details" line for "Jumbo" (some readers omit "Jumbo Loans!" text)
        if "Rate Details" in stripped and pending_product:
            if "jumbo" in stripped.lower():
                pending_is_jumbo = True
            i += 1
            continue

        # Look for rate table data rows
        if "| Rate | APR" not in stripped and "| ---" not in stripped:
            rate_match = re.match(
                r"\|\s*(\d+\.\d{2,4})%\s*\|\s*(\d+\.\d{2,4})%\s*(?:\|\s*([-]?\d+\.?\d*)\s*)?\|",
                stripped,
            )
            if rate_match and pending_product:
                rate = float(rate_match.group(1))
                apr = float(rate_match.group(2))
                product = pending_product
                is_jumbo = pending_is_jumbo

                product_lower = product.lower()

                # Skip HELOC / equity products
                if any(x in product_lower for x in ["heloc", "fixed-rate conversion"]):
                    pending_product = None
                    i += 1
                    continue

                is_arm = "arm" in product_lower or "sofr" in product_lower
                is_fha = "fha" in product_lower

                # Extract year
                year_match = re.search(r"(\d+)-[Yy]ear", product)
                if not year_match:
                    pending_product = None
                    i += 1
                    continue

                years = year_match.group(1)

                if is_arm:
                    if years == "5":
                        term = "5/1 ARM"
                    elif years == "7":
                        term = "7/1 ARM"
                    elif years == "10":
                        term = "10/1 ARM"
                    else:
                        term = f"{years}/1 ARM"
                else:
                    term = f"{years}-Year Fixed"

                if is_jumbo:
                    term += " Jumbo"
                if is_fha:
                    term += " FHA"

                entry = {"term": term, "rate": rate, "apr": apr}

                key = (term, rate)
                if is_arm:
                    if key not in {(e["term"], e["rate"]) for e in arm_entries}:
                        arm_entries.append(entry)
                else:
                    if key not in {(e["term"], e["rate"]) for e in fixed_entries}:
                        fixed_entries.append(entry)

                pending_product = None

        i += 1

    # Sort by rate ascending
    fixed_entries.sort(key=lambda x: x["rate"])
    arm_entries.sort(key=lambda x: x["rate"])

    result = {
        "name": "Golden 1 Credit Union",
        "url": "https://www.golden1.com/credit-cards-loans/home-loans/rates",
        "fixed": fixed_entries,
        "arm": arm_entries,
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