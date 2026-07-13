import html as html_module
import re

def scrape(fetch_html):
    url = 'https://www.starone.org/rates/mortgage-rates'
    html_content = fetch_html(url)
    
    # Strip HTML tags and normalize whitespace
    text = html_module.unescape(html_content)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = ' '.join(text.split())
    
    fixed_pattern = re.compile(
        r"(\d+)-year mortgage at (\d+\.\d{2,4})%\s*\((\d+\.\d{2,4})%\s*APR",
        re.IGNORECASE
    )
    
    arm_pattern = re.compile(
        r"(\d+)-Year Fixed-to-Adjustable-Rate Mortgage.*?is (\d+\.\d{2,4})%\s*\((\d+\.\d{2,4})%\s*APR for conforming",
        re.IGNORECASE
    )
    
    fixed_entries = []
    seen_fixed = set()
    for match in fixed_pattern.finditer(text):
        term = f"{match.group(1)}-Year Fixed"
        rate = float(match.group(2))
        apr = float(match.group(3))
        entry_key = (term, rate, apr)
        if entry_key not in seen_fixed:
            seen_fixed.add(entry_key)
            fixed_entries.append({
                "term": term,
                "rate": rate,
                "apr": apr
            })
            
    arm_entries = []
    seen_arm = set()
    for match in arm_pattern.finditer(text):
        term = f"{match.group(1)}/1 ARM"
        rate = float(match.group(2))
        apr = float(match.group(3))
        entry_key = (term, rate, apr)
        if entry_key not in seen_arm:
            seen_arm.add(entry_key)
            arm_entries.append({
                "term": term,
                "rate": rate,
                "apr": apr
            })
            
    return {
        "name": "Star One Credit Union",
        "url": url,
        "fixed": fixed_entries,
        "arm": arm_entries
    }
