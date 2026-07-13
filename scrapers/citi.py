"""Citi mortgage rate scraper (via Jina reader)."""

import re
import subprocess
import json


def scrape(fetch_html):
    jina_url = "https://r.jina.ai/https://www.citi.com/mortgage/refinance-rates"

    result = subprocess.run(
        ["curl", "-sL", "--max-time", "20", jina_url],
        capture_output=True, text=True, timeout=25,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl exited {result.returncode}")
    text = result.stdout
    if not text or len(text) < 200:
        raise RuntimeError(f"Citi: Jina returned {len(text) if text else 0} chars")

    fixed_entries = []
    arm_entries = []

    # Pattern: | ## 15-Year Fixed | 5.625% | 5.844% | 1.000 | $3,706.79...
    # or       | ## 30-Year Jumbo | 6.25% | 6.357% | 1.000 | ...
    pattern = re.compile(
        r"\|\s*##\s*(.+?)\s*\|\s*(\d+\.\d{2,4})%\s*\|\s*(\d+\.\d{2,4})%"
    )

    for match in pattern.finditer(text):
        name = match.group(1).strip()
        rate = float(match.group(2))
        apr = float(match.group(3))

        nl = name.lower()

        # Determine term
        is_arm = any(x in nl for x in ["arm", "adjustable"])
        is_jumbo = "jumbo" in nl
        is_fha = "fha" in nl
        is_va = "va" in nl

        if is_arm:
            yr = re.search(r"(\d+)/", name)
            if yr:
                years = yr.group(1)
                term = f"{years}/1 ARM"
            else:
                continue
        else:
            yr = re.search(r"(\d+)-year", name, re.IGNORECASE)
            if yr:
                term = f"{yr.group(1)}-Year Fixed"
            else:
                continue

        if is_jumbo:
            term += " Jumbo"
        if is_fha:
            term += " FHA"
        if is_va:
            term += " VA"

        entry = {"term": term, "rate": rate, "apr": apr}

        if is_arm:
            arm_entries.append(entry)
        else:
            fixed_entries.append(entry)

    fixed_entries.sort(key=lambda x: x["rate"])
    arm_entries.sort(key=lambda x: x["rate"])

    return {
        "name": "Citi",
        "url": "https://www.citi.com/mortgage/refinance-rates",
        "fixed": fixed_entries,
        "arm": arm_entries,
    }


if __name__ == "__main__":
    result = scrape(None)
    print(json.dumps(result, indent=2))