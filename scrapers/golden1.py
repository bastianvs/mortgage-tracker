import re, httpx

def scrape(fetch_html):
    url = 'https://www.golden1.com/rates/mortgage-rates'
    fixed = []
    arm = []

    try:
        html = fetch_html(url, timeout=5)
    except Exception:
        return {"name": "Golden 1 Credit Union", "url": url, "fixed": [], "arm": []}

    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)

    for m in re.finditer(r'(\d+)\s*(?:Year|Yr)[.\s]*(?:Fixed|Mortgage|ARM)', text, re.IGNORECASE):
        ctx = text[max(0, m.start()-100):m.end()+100]
        percentages = re.findall(r'(\d+\.\d{2,4})\s*%', ctx)
        if len(percentages) >= 1:
            try:
                is_arm = 'arm' in ctx.lower() or 'adjustable' in ctx.lower()
                term = f"{m.group(1)}-Year Fixed" if not is_arm else f"{m.group(1)}/1 ARM"
                rate = float(percentages[0])
                apr = float(percentages[1]) if len(percentages) > 1 else rate
                if 1.0 < rate < 20.0:
                    fixed.append({"term": term, "rate": rate, "apr": apr})
            except Exception:
                pass

    return {
        "name": "Golden 1 Credit Union",
        "url": url,
        "fixed": fixed,
        "arm": arm
    }