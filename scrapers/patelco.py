import re

def scrape(fetch_html):
    url = 'https://www.patelco.org/credit-cards-and-loans/home-loans/mortgage'
    html = fetch_html(url)
    
    # Strip HTML tags and normalize whitespace
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)
    
    fixed = []
    seen_fixed = set()
    fixed_pattern = re.compile(
        r'(\d+)-Year Fixed(?:\s+(?:High Balance|Jumbo))?\s+\$[\d,]+\s+to\s+\$[\d,]+\s+(\d+\.\d{2,4})%\s+(\d+\.\d{2,4})%',
        re.IGNORECASE
    )
    for match in fixed_pattern.finditer(text):
        term = f"{match.group(1)}-Year Fixed"
        rate = float(match.group(2))
        apr = float(match.group(3))
        entry = (term, rate, apr)
        if entry not in seen_fixed:
            seen_fixed.add(entry)
            fixed.append({
                "term": term,
                "rate": rate,
                "apr": apr
            })
            
    arm = []
    seen_arm = set()
    arm_pattern = re.compile(
        r'(\d+/\d+)\s+30-Year Adjustable(?:\s+Jumbo)?\s+\$[\d,]+\s+to\s+\$[\d,]+\s+(\d+\.\d{2,4})%\s+(\d+\.\d{2,4})%',
        re.IGNORECASE
    )
    for match in arm_pattern.finditer(text):
        term = f"{match.group(1)} ARM"
        rate = float(match.group(2))
        apr = float(match.group(3))
        entry = (term, rate, apr)
        if entry not in seen_arm:
            seen_arm.add(entry)
            arm.append({
                "term": term,
                "rate": rate,
                "apr": apr
            })
            
    return {
        "name": "PatelCo Credit Union",
        "url": url,
        "fixed": fixed,
        "arm": arm
    }
