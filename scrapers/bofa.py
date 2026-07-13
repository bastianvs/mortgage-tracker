import re
from selectolax.parser import HTMLParser

def scrape(fetch_html):
    url = 'https://www.bankofamerica.com/mortgage/mortgage-rates/'
    fixed = []
    arm = []
    seen_fixed = set()
    seen_arm = set()

    try:
        html = fetch_html(url)
    except Exception:
        return {"name": "Bank of America", "url": url, "fixed": [], "arm": []}

    tree = HTMLParser(html)

    # BofA often has rate data in script tags with JSON config
    for script in tree.css('script'):
        content = script.text()
        if not content:
            continue
        # Look for rate objects
        for m in re.finditer(r'interestRate["\':]\s*["\']?(\d+\.\d+)["\']?', content):
            ctx = content[max(0, m.start()-200):m.end()+100]
            # Try to find term
            term_m = re.search(r'(?:productName|term|product_type|loanType)["\':]\s*["\']([^"\']+)["\']', ctx)
            apr_m = re.search(r'apr["\':]\s*["\']?(\d+\.\d+)["\']?', ctx)

            term = term_m.group(1) if term_m else "Unknown"
            rate = float(m.group(1))
            apr = float(apr_m.group(1)) if apr_m else rate

            if not (1.0 < rate < 20.0):
                continue

            # Clean term
            term_clean = term.replace("-Rate", "").replace("Rate", "").strip()
            m_yr = re.search(r'(\d+)\s*Year', term_clean, re.IGNORECASE)
            if m_yr:
                if 'arm' in term_clean.lower() or 'adjustable' in term_clean.lower():
                    term_clean = f"{m_yr.group(1)}/1 ARM"
                    is_arm = True
                else:
                    term_clean = f"{m_yr.group(1)}-Year Fixed"
                    is_arm = False
            else:
                is_arm = 'arm' in term_clean.lower() or 'adjustable' in term_clean.lower()

            entry = (term_clean, rate, apr)
            target = arm if is_arm else fixed
            seen = seen_arm if is_arm else seen_fixed
            if entry not in seen:
                seen.add(entry)
                target.append({"term": term_clean, "rate": rate, "apr": apr})

    # Also check for __NEXT_DATA__ or embedded page data
    nd_match = re.search(r'__NEXT_DATA__"[^>]*>({.*?})<', html, re.DOTALL)
    if nd_match:
        import json
        try:
            data = json.loads(nd_match.group(1))
            # BofA might embed rates differently
            text = json.dumps(data)
            for m in re.finditer(r'(?:rate|apr)["\']:\s*["\']?(\d+\.\d+)["\']?', text):
                pass  # Already caught by regex above
        except Exception:
            pass

    # Fallback: search for rate table patterns in text
    if not fixed and not arm:
        text = ' '.join(tree.text().split())
        for m in re.finditer(r'(\d+)\s*[Yy]ear\s+(?:Fixed|ARM)', text):
            ctx = text[max(0, m.start()-50):m.end()+80]
            rates_found = re.findall(r'(\d+\.\d+)\s*%', ctx)
            if len(rates_found) >= 2:
                try:
                    term = f"{m.group(1)}-Year Fixed" if "Fixed" in m.group() else f"{m.group(1)}/1 ARM"
                    rate = float(rates_found[0])
                    apr = float(rates_found[1])
                    is_arm = "arm" in term.lower()
                    entry = (term, rate, apr)
                    target = arm if is_arm else fixed
                    seen = seen_arm if is_arm else seen_fixed
                    if entry not in seen:
                        seen.add(entry)
                        target.append({"term": term, "rate": rate, "apr": apr})
                except Exception:
                    pass

    return {
        "name": "Bank of America",
        "url": url,
        "fixed": fixed,
        "arm": arm
    }