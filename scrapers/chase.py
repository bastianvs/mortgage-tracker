import re
import json

def scrape(fetch_html):
    url = 'https://www.chase.com/personal/mortgage/mortgage-rates'
    fixed = []
    arm = []
    seen_fixed = set()
    seen_arm = set()

    try:
        html = fetch_html(url)
    except Exception:
        return {"name": "JPMorgan Chase", "url": url, "fixed": [], "arm": []}

    # Chase uses __NEXT_DATA__ on their rate pages
    nd_match = re.search(r'__NEXT_DATA__"[^>]*>\s*(.*?)\s*</script>', html, re.DOTALL)
    if nd_match:
        content = nd_match.group(1)
        content = content.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
        try:
            data = json.loads(content)
            search_rates(data, fixed, arm, seen_fixed, seen_arm)
        except json.JSONDecodeError:
            pass

    # Try the internal API (needs auth headers from page)
    if not fixed and not arm:
        try_api(html, fixed, arm, seen_fixed, seen_arm)

    # Text pattern matching as last resort
    if not fixed and not arm:
        search_html_for_rates(html, fixed, arm, seen_fixed, seen_arm)

    return {
        "name": "JPMorgan Chase",
        "url": url,
        "fixed": fixed,
        "arm": arm
    }


def try_api(html, fixed, arm, seen_fixed, seen_arm):
    """Try Chase rate API. Requires auth headers embedded in page."""
    # The API needs a bearer token from the page
    # For now, this returns empty since we can't auth
    import httpx
    urls = [
        'https://apix.chase.com/home-lending/sales-relationship/lead-management/mortgage-info/v1/rates',
    ]
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json',
        'Referer': 'https://www.chase.com/personal/mortgage/mortgage-rates',
    }
    for url in urls:
        try:
            r = httpx.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                search_rates(data, fixed, arm, seen_fixed, seen_arm)
                if fixed or arm:
                    return
        except Exception:
            pass


def search_rates(data, fixed, arm, seen_fixed, seen_arm):
    """Recursively search for rate data in parsed JSON."""
    if isinstance(data, dict):
        name = data.get('name') or data.get('productName') or data.get('label') or data.get('product')
        rate = data.get('rate') or data.get('interestRate') or data.get('productRate')
        apr = data.get('apr') or data.get('aprRate')

        if name and rate is not None:
            try:
                rate = float(rate)
                if apr is not None:
                    apr = float(apr)
                else:
                    apr = rate
                if 1.0 < rate < 20.0:
                    name_str = str(name)
                    term = clean_term(name_str)
                    is_arm = 'arm' in term.lower() or 'adjustable' in term.lower() or '/' in term
                    entry = (term, rate, apr)
                    target = arm if is_arm else fixed
                    seen = seen_arm if is_arm else seen_fixed
                    if entry not in seen:
                        seen.add(entry)
                        target.append({"term": term, "rate": rate, "apr": apr})
            except (ValueError, TypeError):
                pass
        for v in data.values():
            search_rates(v, fixed, arm, seen_fixed, seen_arm)
    elif isinstance(data, list):
        for item in data:
            search_rates(item, fixed, arm, seen_fixed, seen_arm)


def search_html_for_rates(html, fixed, arm, seen_fixed, seen_arm):
    """Fallback: search raw HTML for rate patterns."""
    for m in re.finditer(r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>', html, re.DOTALL):
        try:
            data = json.loads(m.group(1))
            search_rates(data, fixed, arm, seen_fixed, seen_arm)
        except Exception:
            pass
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)
    for m in re.finditer(r'(\d+)\s*[-/]?\s*Year\s+(Fixed|ARM|Adjustable)', text, re.IGNORECASE):
        ctx = text[max(0, m.start()-60):m.end()+80]
        rates_found = re.findall(r'(\d+\.\d{2,4})\s*%', ctx)
        if len(rates_found) >= 1:
            try:
                term = f"{m.group(1)}-Year Fixed" if m.group(2).lower() == 'fixed' else f"{m.group(1)}/1 ARM"
                rate = float(rates_found[0])
                apr = float(rates_found[1]) if len(rates_found) > 1 else rate
                is_arm = m.group(2).lower() in ('arm', 'adjustable')
                entry = (term, rate, apr)
                target = arm if is_arm else fixed
                seen = seen_arm if is_arm else seen_fixed
                if entry not in seen:
                    seen.add(entry)
                    target.append({"term": term, "rate": rate, "apr": apr})
            except Exception:
                pass


def clean_term(name):
    name = name.replace(" - Rate", "").replace(" Rate", "").strip()
    m_fixed = re.search(r'(\d+)\s*Year\s+Fixed', name, re.IGNORECASE)
    if m_fixed:
        return f"{m_fixed.group(1)}-Year Fixed"
    m_arm = re.search(r'(\d+)\s*Year\s+(?:ARM|Adjustable)', name, re.IGNORECASE)
    if m_arm:
        return f"{m_arm.group(1)}/1 ARM"
    return name