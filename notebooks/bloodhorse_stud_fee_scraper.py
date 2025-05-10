#!/usr/bin/env python
"""
bloodhorse_stud_fee_scraper.py
--------------------------------
Given an Excel file with columns `Sire` and `sale_year`, this script:

1. Uses Google Search to discover the first BloodHorse “worldwide sales
   results” page for the sire and year (or ±1 year if needed).
2. Extracts the six‑digit BloodHorse stallion ID from that URL.
3. Walks every sales‑results page from 2006‑2025 for that sire,
   harvesting the *Stud Fee* listed in the **Weanlings** table.
   (Weanlings sold in YEAR correspond to the STUD FEE charged the
   previous YEAR, so `stud_fee_year = sale_year - 1`.)
4. Writes a tidy CSV:  `Sire,stud_fee_year,stud_fee_usd`.

The script is intentionally polite to BloodHorse:
   • Sets a realistic User‑Agent header  
   • Sleeps 1‑3 s between every HTTP request  
   • Retries once on common transient failures
"""
import argparse
import random
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS 

# ---------------------------------------------------------------------
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
YEARS_TO_CRAWL = range(2006, 2026)  # sales‑results pages we will visit
SEARCH_TEMPLATE = '{} {} worldwide sales results bloodhorse site:bloodhorse.com'
BH_URL_RE = re.compile(r'/stallions/(\d{6})/([^/]+)/auctions/(\d{4})')
STUD_FEE_RE = re.compile(r'(\d{4})\s*Stud Fee.*?\$([\d,]+)', re.I | re.S)


# ---------------------------------------------------------------------
def polite_get(url: str, tries: int = 2, timeout: int = 10) -> Optional[str]:
    """GET with headers, retry once, random sleep."""
    for attempt in range(tries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp.text
        except requests.RequestException:
            pass
        # Back‑off
        time.sleep(random.uniform(2, 4))
    return None


def find_initial_bloodhorse_url(sire: str, sale_year: int) -> Optional[Tuple[str, str]]:
    """
    Query DuckDuckGo for the BloodHorse auctions page.
    Tries given year, then +1 and -1.  Returns (stallion_id, slug) or None.
    """
    with DDGS() as ddgs:
        for delta in [0, 1, -1]:
            y = sale_year + delta
            q = f"{sire} {y} worldwide sales results bloodhorse"
            for r in ddgs.text(q, max_results=15):
                url = r.get("href") or r.get("url")
                if not url:
                    continue
                m = BH_URL_RE.search(url)
                if m:
                    stallion_id, slug, _ = m.groups()
                    return stallion_id, slug
            time.sleep(random.uniform(1, 2))   # be polite to DDG
    return None

from bs4 import BeautifulSoup
import re


def stud_fee_from_weanlings(html: str) -> dict[int, int]:
    """
    Return {stud_fee_year: stud_fee_usd} for the Weanlings tab only.
    """
    soup = BeautifulSoup(html, "lxml")

    # find the first Weanlings <ul class="tabs"><li> or the header string
    weanlings_li = soup.find("li", string=re.compile(r"\bWeanlings\b", re.I))
    if not weanlings_li:
        return {}

    # the <ul class="tabs"> is the parent; the corresponding tabPane is next
    tab_ul = weanlings_li.find_parent("ul", class_="tabs")
    tab_pane = tab_ul.find_next_sibling("div", class_="contentBlock")
    if not tab_pane:
        return {}

    # within that pane, the <li> that starts with 'YYYY Stud Fee'
    fee_li = tab_pane.find("li", string=re.compile(r"^\d{4}\s+Stud\s+Fee", re.I))
    if not fee_li:
        return {}

    m = re.match(r"(?P<yr>\d{4})\s+Stud\s+Fee:\s+\$(?P<amt>[\d,]+)", fee_li.text)
    if not m:
        return {}

    yr = int(m.group("yr"))
    amt = int(m.group("amt").replace(",", ""))
    return {yr: amt}


def scrape_page_for_stud_fee(html: str) -> Dict[int, int]:
    """
    Parse a BloodHorse auctions page and pull all '<YEAR> Stud Fee  $<amount>'
    patterns. Returns {stud_fee_year: fee}.
    """
    fees = {}
    for m in STUD_FEE_RE.finditer(html):
        fee_year = int(m.group(1))
        fee_amt = int(m.group(2).replace(",", ""))
        fees[fee_year] = fee_amt
    return fees


def harvest_sire_fees(stallion_id: str, sire_slug: str) -> List[Tuple[int, int]]:
    """
    Walk every YEAR in YEARS_TO_CRAWL and return list of
    (stud_fee_year, fee) pairs (duplicate years removed).
    """
    seen: Dict[int, int] = {}
    for sales_year in YEARS_TO_CRAWL:
        url = (
            f"https://www.bloodhorse.com/stallion-register/stallions/"
            f"{stallion_id}/{sire_slug}/auctions/{sales_year}"
        )
        html = polite_get(url)
        if not html:
            continue

        # A Weanlings table must exist to contain a stud fee.
        if "Weanlings" not in html:
            continue

        page_fees = stud_fee_from_weanlings(html)

        # For each Stud Fee we found, accept if not already captured.
        for fee_year, fee in page_fees.items():
            if fee_year not in seen:
                seen[fee_year] = fee

        # be nice to the server
        time.sleep(random.uniform(1, 3))

    # Return as sorted list
    return sorted(seen.items())


# ---------------------------------------------------------------------
def load_sire_file(path: Path) -> pd.DataFrame:
    """
    Load a sire list from .csv, .xls, or .xlsx.
    The file must have exactly these two columns: Sire, sale_year
    """
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    elif path.suffix.lower() in {".xls", ".xlsx"}:
        # specify an engine to silence pandas' guess‑engine warning
        df = pd.read_excel(path, engine="openpyxl")
    else:
        raise ValueError("Input must be .csv, .xls, or .xlsx")

    if set(df.columns) != {"Sire", "sale_year"}:
        raise ValueError("File must contain exactly the columns: Sire, sale_year")
    return df



def main():
    parser = argparse.ArgumentParser(description="BloodHorse stud‑fee scraper")
    parser.add_argument("--input", required=True, help="Excel file with Sire & sale_year")
    parser.add_argument("--output", required=True, help="CSV file to write")
    args = parser.parse_args()

    sire_df = load_sire_file(Path(args.input))

    rows: List[Tuple[str, int, int]] = []

    for idx, (sire, sale_year) in sire_df.iterrows():
        print(f"▶ Processing {sire} ({sale_year})...")
        initial = find_initial_bloodhorse_url(sire, int(sale_year))
        if not initial:
            print(f"  ⚠️  No BloodHorse link found for {sire}; skipping.")
            continue
        stallion_id, sire_slug = initial
        print(f"  🆔 Stallion ID: {stallion_id}")

        fee_pairs = harvest_sire_fees(stallion_id, sire_slug)
        if not fee_pairs:
            print(f"  ⚠️  No stud fees found for {sire}.")
            continue

        for stud_fee_year, fee_usd in fee_pairs:
            rows.append((sire, stud_fee_year, fee_usd))

    out_df = pd.DataFrame(rows, columns=["Sire", "stud_fee_year", "stud_fee_usd"])
    out_df.to_csv(args.output, index=False)
    print(f"✅ Finished. Wrote {len(out_df)} rows to {args.output}")


if __name__ == "__main__":
    main()
