import re
import json
import datetime
import uuid
import httpx
from selectolax.parser import HTMLParser

def clean_term(name):
    name = name.replace("-Rate", "").replace(" Rate", "")
    m_fixed = re.search(r'(\d+)-Year\s+Fixed', name, re.IGNORECASE)
    if m_fixed:
        return f"{m_fixed.group(1)}-Year Fixed"
    m_fixed_short = re.search(r'(\d+)-Year', name, re.IGNORECASE)
    if m_fixed_short and "fixed" in name.lower():
        return f"{m_fixed_short.group(1)}-Year Fixed"
    m_arm = re.search(r'(\d+/\d+)-Month\s+ARM', name, re.IGNORECASE)
    if m_arm:
        return f"{m_arm.group(1)} ARM"
    m_arm_simple = re.search(r'(\d+/\d+)\s+ARM', name, re.IGNORECASE)
    if m_arm_simple:
        return f"{m_arm_simple.group(1)} ARM"
    m_arm_dash = re.search(r'(\d+)-Month\s+ARM', name, re.IGNORECASE)
    if m_arm_dash:
        return f"{m_arm_dash.group(1)} ARM"
    m_arm_month = re.search(r'(\d+/\d+)-Month', name, re.IGNORECASE)
    if m_arm_month:
        return f"{m_arm_month.group(1)} ARM"
    return name

def extract_rates_from_json(data):
    results = []
    if isinstance(data, dict):
        product_name = data.get('product_name') or data.get('name') or data.get('term')
        rate = data.get('interest_rate') or data.get('rate') or data.get('interestRate')
        apr = data.get('apr') or data.get('apr_rate')
        if product_name and rate is not None and apr is not None:
            try:
                rate_val = float(rate)
                apr_val = float(apr)
                if 1.0 < rate_val < 20.0 and 1.0 < apr_val < 20.0:
                    term = clean_term(str(product_name))
                    is_arm = "arm" in term.lower() or "/" in term or data.get('product_type') == 'ADJUSTABLE'
                    results.append((term, rate_val, apr_val, is_arm))
            except Exception:
                pass
        for k, v in data.items():
            results.extend(extract_rates_from_json(v))
    elif isinstance(data, list):
        for item in data:
            results.extend(extract_rates_from_json(item))
    return results

def parse_html_for_rates(html):
    fixed = []
    arm = []
    seen_fixed = set()
    seen_arm = set()
    tree = HTMLParser(html)

    for el in tree.css('[data-rate], [data-apr]'):
        rate_str = el.attributes.get('data-rate')
        apr_str = el.attributes.get('data-apr')
        term_str = el.attributes.get('data-term') or el.text().strip()
        if rate_str and apr_str:
            try:
                rate = float(re.sub(r'[^\d.]', '', rate_str))
                apr = float(re.sub(r'[^\d.]', '', apr_str))
                term = clean_term(term_str)
                entry = (term, rate, apr)
                is_arm = "arm" in term.lower() or "/" in term
                target_list = arm if is_arm else fixed
                target_seen = seen_arm if is_arm else seen_fixed
                if entry not in target_seen:
                    target_seen.add(entry)
                    target_list.append({"term": term, "rate": rate, "apr": apr})
            except Exception:
                pass

    if not fixed and not arm:
        for row in tree.css('tr'):
            cells = [c.text().strip() for c in row.css('td, th')]
            if len(cells) >= 3:
                term_cand = cells[0]
                rates_cand = []
                for cell in cells[1:]:
                    m = re.search(r'(\d+\.\d+)%', cell)
                    if m:
                        rates_cand.append(float(m.group(1)))
                if len(rates_cand) >= 2:
                    rate = rates_cand[0]
                    apr = rates_cand[1]
                    term = clean_term(term_cand)
                    if "fixed" in term.lower() or "arm" in term.lower() or "/" in term or "year" in term.lower():
                        entry = (term, rate, apr)
                        is_arm = "arm" in term.lower() or "/" in term
                        target_list = arm if is_arm else fixed
                        target_seen = seen_arm if is_arm else seen_fixed
                        if entry not in target_seen:
                            target_seen.add(entry)
                            target_list.append({"term": term, "rate": rate, "apr": apr})

    if not fixed and not arm:
        for script in tree.css('script'):
            content = script.text()
            if not content:
                continue
            for match in re.finditer(r'({.*?})|(\[.*?\])', content, re.DOTALL):
                try:
                    data = json.loads(match.group(0))
                    extracted = extract_rates_from_json(data)
                    for term, rate, apr, is_arm in extracted:
                        entry = (term, rate, apr)
                        target_list = arm if is_arm else fixed
                        target_seen = seen_arm if is_arm else seen_fixed
                        if entry not in target_seen:
                            target_seen.add(entry)
                            target_list.append({"term": term, "rate": rate, "apr": apr})
                except Exception:
                    pass

    if not fixed and not arm:
        text = ' '.join(tree.text().split())
        pattern = re.compile(
            r'(\d+(?:/\d+)?-Year\s+(?:Fixed|ARM|Adjustable)(?:\s+Rate)?)\s+(\d+\.\d{2,4})%\s+(\d+\.\d{2,4})%',
            re.IGNORECASE
        )
        for match in pattern.finditer(text):
            term = clean_term(match.group(1))
            rate = float(match.group(2))
            apr = float(match.group(3))
            entry = (term, rate, apr)
            is_arm = "arm" in term.lower() or "/" in term
            target_list = arm if is_arm else fixed
            target_seen = seen_arm if is_arm else seen_fixed
            if entry not in target_seen:
                target_seen.add(entry)
                target_list.append({"term": term, "rate": rate, "apr": apr})
    return fixed, arm

def scrape(fetch_html):
    url = 'https://www.wellsfargo.com/mortgage/rates/'
    fixed = []
    arm = []
    seen_fixed = set()
    seen_arm = set()

    html = ''
    try:
        html = fetch_html(url)
    except Exception:
        pass

    if html:
        f, a = parse_html_for_rates(html)
        fixed.extend(f)
        arm.extend(a)

    if not fixed and not arm:
        fallback_url = 'https://www.wellsfargo.com/mortgage/rates/purchase-rates'
        html_fallback = ''
        try:
            html_fallback = fetch_html(fallback_url)
        except Exception:
            pass
        if html_fallback:
            f, a = parse_html_for_rates(html_fallback)
            fixed.extend(f)
            arm.extend(a)

    if not fixed and not arm:
        html_for_host = html or html_fallback
        m_host = re.search(r'homelendingToolsHost\s*=\s*["\']([^"\']+)["\']', html_for_host) if html_for_host else None
        host = m_host.group(1).replace(r'\/', '/') if m_host else "https://connect.secure.wellsfargo.com"
        api_url = host.rstrip('/') + '/xapi/product-service-research/homelending-tools/v1/rates/purchase'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'X-WF-REQUEST-DATE': datetime.datetime.utcnow().isoformat() + 'Z',
            'X-CORRELATION-ID': str(uuid.uuid4()),
            'X-WF-CLIENT-ID': 'WU',
            'X-REQUEST-ID': str(uuid.uuid4()),
            'Content-Type': 'application/json'
        }
        try:
            r = httpx.get(api_url, headers=headers, timeout=20)
            if r.status_code == 200:
                data = r.json()
                extracted = extract_rates_from_json(data)
                for term, rate, apr, is_arm in extracted:
                    entry = (term, rate, apr)
                    target_list = arm if is_arm else fixed
                    target_seen = seen_arm if is_arm else seen_fixed
                    if entry not in target_seen:
                        target_seen.add(entry)
                        target_list.append({"term": term, "rate": rate, "apr": apr})
        except Exception:
            pass

    return {
        "name": "Wells Fargo",
        "url": url,
        "fixed": fixed,
        "arm": arm
    }