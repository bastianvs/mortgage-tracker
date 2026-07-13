"""
Scrape national average mortgage rates from Freddie Mac PMMS
(Primary Mortgage Market Survey) - updated weekly on Thursdays.
"""

import re
from datetime import datetime, timezone

def scrape(fetch_html):
    url = 'https://www.freddiemac.com/pmms/'
    result = {
        "name": "Freddie Mac PMMS",
        "url": url,
        "rates": {},
    }

    try:
        html = fetch_html(url)
    except Exception as e:
        result["error"] = str(e)
        return result

    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)

    # Extract the key table data
    # "30-year Fixed-Rate Mortgage 6.49% 15-year Fixed-Rate Mortgage 5.82%"
    m = re.search(
        r'30-year Fixed-Rate Mortgage\s+(\d+\.\d+)%.*?'
        r'15-year Fixed-Rate Mortgage\s+(\d+\.\d+)%',
        text, re.IGNORECASE
    )
    if m:
        result["rates"]["30_year_fixed"] = float(m.group(1))
        result["rates"]["15_year_fixed"] = float(m.group(2))

    # Also grab the as-of date
    date_m = re.search(r'as of\s+(\w+\s+\d+,\s+\d{4})', text, re.IGNORECASE)
    if date_m:
        try:
            from datetime import datetime
            dt = datetime.strptime(date_m.group(1), '%B %d, %Y')
            result["as_of"] = dt.strftime('%Y-%m-%d')
        except Exception:
            pass

    return result