# Mortgage Rate Tracker 🏠

Daily mortgage rate tracking from major US lenders and credit unions, served at **[rates.bastian.services](https://rates.bastian.services/)**.

## What It Does

Fetches current mortgage rates from multiple sources every day, stores them historically, and displays them on a clean web dashboard with charts.

### Rate Sources

**Banks:**
- Bank of America
- Chase
- Citi
- Wells Fargo
- US Bank

**Credit Unions (SF Bay Area):**
- PatelCo Credit Union
- Star One Credit Union
- Golden 1 Credit Union

**National Benchmark:**
- Freddie Mac PMMS (Primary Mortgage Market Survey)

### Loan Types Tracked

- 30-Year Fixed
- 15-Year Fixed
- 20-Year Fixed
- 10-Year Fixed
- 5/1 ARM
- 7/1 ARM
- 10/1 ARM
- Jumbo loans (where available)

## Project Structure

```
mortgage-tracker/
├── fetch_rates.py       # Main scraper — fetches all sources, outputs daily JSON
├── build_history.py     # Compiles daily snapshots into history.json for charts
├── fix.sh               # Full deploy script: scrape → commit → push → gh-pages
├── scrapers/            # Per-institution scraping modules
│   ├── patelco.py
│   ├── starone.py
│   ├── golden1.py
│   ├── bofa.py
│   ├── chase.py
│   ├── citi.py
│   ├── wellsfargo.py
│   ├── usbank.py
│   └── pmms.py
├── data/                # Daily rate snapshots (rates-YYYY-MM-DD.json)
├── site/                # Static website
│   ├── index.html       # Dashboard with summary cards, charts, lender tables
│   └── data/
│       ├── latest.json   # Latest rates for the website
│       └── history.json  # 90-day history for charts
└── vercel.json          # Vercel deployment config (outputDirectory: site)
```

## How It Works

1. **`fetch_rates.py`** scrapes each lender's website for current rates
2. Outputs: `data/rates-YYYY-MM-DD.json` (daily snapshot) + `site/data/latest.json` (live data)
3. **`build_history.py`** compiles daily snapshots into `site/data/history.json` (90-day chart data)
4. The static site at `site/index.html` fetches `latest.json` and `history.json` to render everything client-side
5. **`fix.sh`** is the full pipeline — it scrapes, commits, and force-deploys the site to GitHub Pages on the `gh-pages` branch

## Running Locally

### Prerequisites

- Python 3.10+
- `httpx` (`pip install httpx`)

### Fetch Today's Rates

```bash
python3 fetch_rates.py
```

### Build Chart History

```bash
python3 build_history.py
```

### View the Site Locally

```bash
cd site && python3 -m http.server 8080
# Open http://localhost:8080
```

## Deployment

### GitHub Pages (current)

The site is deployed to GitHub Pages from the `gh-pages` branch. The domain `rates.bastian.services` is configured via a CNAME record and Cloudflare proxy.

```bash
./fix.sh   # Scrape, commit, force-deploy to gh-pages
```

### Vercel

The `vercel.json` configures the output directory as `site/`. To deploy on Vercel:

1. Connect the repo in the Vercel dashboard
2. Set framework to "Other" (static site)
3. `vercel.json` handles the rest

## Data Format

### latest.json

```json
{
  "date": "2026-07-13",
  "summary": {
    "30_year_fixed_avg": 6.625,
    "15_year_fixed_avg": 5.875,
    "5_1_arm_avg": 5.8
  },
  "institutions": {
    "patelco": {
      "name": "PatelCo Credit Union",
      "fixed": [{ "term": "30-Year Fixed", "rate": 6.625, "apr": 6.71 }],
      "arm": [{ "term": "5/1 ARM", "rate": 5.8, "apr": 6.05 }]
    }
  }
}
```

### history.json

```json
[
  {
    "date": "2026-07-13",
    "summary": {
      "30_year_fixed": 6.625,
      "15_year_fixed": 5.875,
      "5_1_arm": 5.8
    }
  }
]
```

## Assumptions

All rates assume:
- 780+ credit score
- Conforming loan limits
- 20% down payment
- Single-family detached home
- Purchase money mortgage (not refinance)