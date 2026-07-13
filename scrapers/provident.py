import re

def scrape(fetch_html):
    url = 'https://www.providentcu.org/rates/'
    fixed = []
    arm = []
    seen_fixed = set()
    seen_arm = set()

    try:
        html = fetch_html(url)
    except Exception:
        return {"name": "Provident Credit Union", "url": url, "fixed": [], "arm": []}

    # Strip tags and look for mortgage rates in text
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)

    # Look for mortgage-specific rate patterns
    for m in re.finditer(r'(\d+)\s*(?:Year|Yr)[.\s]*(?:Fixed|Mortgage|ARM)', text, re.IGNORECASE):
        ctx = text[max(0, m.start()-100):m.end()+100]
        percentages = re.findall(r'(\d+\.\d{2,4})\s*%', ctx)
        if len(percentages) >= 1:
            try:
                is_arm = 'arm' in ctx.lower() or 'adjustable' in ctx.lower()
                term = f"{m.group(1)}-Year Fixed" if not is_arm else f"{m.group(1)}/1 ARM"
                rate = float(percentages[0])
                apr = float(percentages[1]) if len(percentages) > 1 else rate
                entry = (term, rate, apr)
                target = arm if is_arm else fixed
                seen = seen_arm if is_arm else seen_fixed
                if entry not in seen and 1.0 < rate < 20.0:
                    seen.add(entry)
                    target.append({"term": term, "rate": rate, "apr": apr})
            except Exception:
                pass

    if not fixed and not arm:
        # Try rate sheets page
        try:
            html2 = fetch_html('https://www.providentcu.org/welcome-new-members/rates')
            text2 = re.sub(r'<[^>]+>', ' ', html2)
            text2 = re.sub(r'\s+', ' ', text2)
            for m in re.finditer(r'(\d+)\s*(?:Year|Yr)[.\s]*(?:Fixed|Mortgage|ARM)', text2, re.IGNORECASE):
                ctx = text2[max(0, m.start()-100):m.end()+100]
                percentages = re.findall(r'(\d+\.\d{2,4})\s*%', ctx)
                if len(percentages) >= 1:
                    try:
                        is_arm = 'arm' in ctx.lower() or 'adjustable' in ctx.lower()
                        term = f"{m.group(1)}-Year Fixed" if not is_arm else f"{m.group(1)}/1 ARM"
                        rate = float(percentages[0])
                        apr = float(percentages[1]) if len(percentages) > 1 else rate
                        entry = (term, rate, apr)
                        target = arm if is_arm else fixed
                        seen = seen_arm if is_arm else seen_fixed
                        if entry not in seen and 1.0 < rate < 20.0:
                            seen.add(entry)
                            target.append({"term": term, "rate": rate, "apr": apr})
                    except Exception:
                        pass
        except Exception:
            pass

    return {
        "name": "Provident Credit Union",
        "url": url,
        "fixed": fixed,
        "arm": arm
    }