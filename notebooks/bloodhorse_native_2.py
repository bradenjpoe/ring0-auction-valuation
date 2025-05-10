#!/usr/bin/env python
"""
bloodhorse_stud_fee_scraper.py   (search‑free)
----------------------------------------------
Reads a file with columns `Sire, sale_year` (CSV, XLS, or XLSX) and
produces stud fees, **without** using Google.  It:

1. Builds a “probe” URL:
       https://www.bloodhorse.com/stallion-register/stallions/0/<slug>/auctions/2000
   BloodHorse immediately redirects to the canonical URL that contains the
   six‑digit stallion ID – we capture it from the Location header.
2. Walks every auctions page (2006‑2025) for that ID.
3. Scrapes ‘<YEAR> Stud Fee  $<amount>’ rows that live under the
   Weanlings section.
4. Writes `Sire, stud_fee_year, stud_fee_usd` to a CSV.

Usage
-----
pip install pandas requests beautifulsoup4 openpyxl
python bloodhorse_stud_fee_scraper.py --input sires.csv --output stud_fees.csv
"""
import argparse
import random
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
YEARS_TO_CRAWL = range(2006, 2026)
STUD_FEE_RE = re.compile(r'(\d{4})\s*Stud Fee.*?\$([\d,]+)', re.I | re.S)
REDIRECT_RE = re.compile(r'/stallions/(\d{6})/([^/]+)/auctions/')

# ---------------------------------------------------------------------
def polite_get(url: str, tries: int = 2, timeout: int = 10, **kwargs) -> Optional[requests.Response]:
    """GET with headers, retry once, random sleep.  Returns the Response."""
    for _ in range(tries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout, **kwargs)
            return resp
        except requests.RequestException:
            time.sleep(random.uniform(2, 4))
    return None

# ---------------------------------------------------------------------
def slugify(name: str) -> str:
    """Rough slug: lower‑case, spaces -> hyphens, drop non‑alphanum/hyphen."""
    slug = re.sub(r'[^a-z0-9\- ]+', '', name.lower())
    slug = re.sub(r'\s+', '-', slug.strip())
    return slug

def resolve_stallion_id(sire: str) -> Optional[Tuple[str, str]]:
    """
    Fire a probe request with ID=0.  Capture the redirect’s Location header
    to learn the six‑digit ID and canonical slug.
    """
    slug = slugify(sire)
    probe_url = (
        f"https://www.bloodhorse.com/stallion-register/stallions/0/{slug}/auctions/2000"
    )
    resp = polite_get(probe_url, allow_redirects=False)
    if resp is None:
        return None
    if resp.is_redirect or resp.status_code in (301, 302):
        loc = resp.headers.get("Location", "")
        m = REDIRECT_RE.search(loc)
        if m:
            stallion_id, canonical_slug = m.groups()
            return stallion_id, canonical_slug
    return None

# ---------------------------------------------------------------------
def scrape_page_for_stud_fee(html: str) -> Dict[int, int]:
    fees = {}
    for m in STUD_FEE_RE.finditer(html):
        fee_year = int(m.group(1))
        fee_amt = int(m.group(2).replace(",", ""))
        fees[fee_year] = fee_amt
    return fees

def harvest_sire_fees(stallion_id: str, sire_slug: str) -> List[Tuple[int, int]]:
    seen: Dict[int, int] = {}
    for sales_year in YEARS_TO_CRAWL:
        url = (
            f"https://www.bloodhorse.com/stallion-register/stallions/"
            f"{stallion_id}/{sire_slug}/auctions/{sales_year}"
        )
        resp = polite_get(url)
        if resp is None or resp.status_code != 200:
            continue
        html = resp.text
        if "Weanlings" not in html:
            continue
        page_fees = scrape_page_for_stud_fee(html)
        for y, amt in page_fees.items():
            seen.setdefault(y, amt)        # keep first observation only
        time.sleep(random.uniform(1, 3))
    return sorted(seen.items())

# ---------------------------------------------------------------------
def load_sire_file(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    elif path.suffix.lower() in {".xls", ".xlsx"}:
        df = pd.read_excel(path, engine="openpyxl")
    else:
        raise ValueError("Input must be .csv, .xls, or .xlsx")
    if set(df.columns) != {"Sire", "sale_year"}:
        raise ValueError("File must contain exactly columns: Sire, sale_year")
    return df

# ---------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="CSV/XLS/XLSX with Sire & sale_year")
    ap.add_argument("--output", required=True, help="CSV for scraped fees")
    args = ap.parse_args()

    sire_df = load_sire_file(Path(args.input))
    out_rows: List[Tuple[str, int, int]] = []

    for _, (sire, _) in sire_df.iterrows():
        print(f"▶ {sire}: resolving ID … ", end="", flush=True)
        resolved = resolve_stallion_id(sire)
        if not resolved:
            print("NOT FOUND")
            continue
        stallion_id, slug = resolved
        print(stallion_id)

        fee_pairs = harvest_sire_fees(stallion_id, slug)
        for yr, amt in fee_pairs:
            out_rows.append((sire, yr, amt))

    pd.DataFrame(out_rows, columns=["Sire", "stud_fee_year", "stud_fee_usd"]) \
      .to_csv(args.output, index=False)
    print(f"\n✅ Done.  Wrote {len(out_rows)} rows to {args.output}")

if __name__ == "__main__":
    main()
