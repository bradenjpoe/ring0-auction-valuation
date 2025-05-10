#!/usr/bin/env python
"""
bloodhorse_native_scraper.py
----------------------------
Harvests stud‑fee histories for Thoroughbred stallions directly from
BloodHorse.com (no external search engines).

INPUT  : CSV/XLS/XLSX with columns  Sire , sale_year
OUTPUT : CSV  Sire , stud_fee_year , stud_fee_usd

Key steps
---------
1.   Look up each sire via the BloodHorse Stallion‑Register search endpoint:
     https://www.bloodhorse.com/stallion-register/search?keyword=<query>
2.   Extract the stallion ID & URL slug from the first search hit.
3.   Crawl every auctions page 2006‑2025:
     https://www.bloodhorse.com/stallion-register/stallions/ID/slug/auctions/YEAR
     • Parse “<YYYY> Stud Fee  $<amount>” entries under the *Weanlings* section.
     • Each <YYYY> is the stud‑fee year we record (don’t add duplicates).
4.   Write a tidy CSV.

Notes on non‑USA horses (e.g. “Yoshida (JPN)”)
----------------------------------------------
BloodHorse slugs use “name-country” (lowercase) format, **yoshida-jpn**.
The script:
    • First queries the search endpoint with the exact sire string.
    • If no hit, tries the slugified “name‑country” variant.
So you only need to supply the sire as it appears in your file; the
script will find the right form.

Usage
-----
  --quiet     : only warnings/errors
  --debug     : very verbose (URLs, sleeps, page‑level info)

Written for Python 3.8+.
"""
from __future__ import annotations

import argparse
import logging
import random
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# CONFIGURABLE CONSTANTS
# ---------------------------------------------------------------------------
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
YEARS_TO_CRAWL = range(2006, 2026)
SEARCH_URL = (
    "https://www.bloodhorse.com/stallion-register/search?keyword={}"
)
STALLION_HREF_RE = re.compile(
    r'/stallion-register/stallions/(\d{6})/([^"]+)'
)
STUD_FEE_RE = re.compile(
    r'(\d{4})\s*Stud Fee[^$]*\$([\d,]+)', re.I | re.S
)

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTTP HELPERS
# ---------------------------------------------------------------------------
def polite_get(url: str, sleep_range: Tuple[float, float] = (1.0, 2.5),
               tries: int = 3, timeout: int = 12) -> Optional[str]:
    """GET with polite headers + jittered sleep between retries."""
    for attempt in range(tries):
        try:
            log.debug("GET %s", url)
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp.text
            log.debug("  Status %s on attempt %d", resp.status_code, attempt + 1)
        except requests.RequestException as e:
            log.debug("  Request error %s on attempt %d", e, attempt + 1)
        time.sleep(random.uniform(*sleep_range))
    log.warning("  Failed to fetch %s after %d tries", url, tries)
    return None

# ---------------------------------------------------------------------------
# BLOODHORSE LOOKUP
# ---------------------------------------------------------------------------
def slugify_sire(sire: str) -> str:
    """
    Convert "Yoshida (JPN)" -> "yoshida-jpn", "Gio Ponti" -> "gio-ponti".
    Matches BloodHorse slug style.
    """
    sire = sire.strip()
    # capture "(ABC)" country code if present
    m = re.match(r"^(.*?)\s*\((\w{2,4})\)$", sire)
    if m:
        name, country = m.groups()
        base = name.strip()
        slug = re.sub(r"[^\w\s-]", "", base).lower()
        slug = re.sub(r"\s+", "-", slug)
        return f"{slug}-{country.lower()}"
    # USA horses—just hyphenate & lower
    slug = re.sub(r"[^\w\s-]", "", sire).lower()
    slug = re.sub(r"\s+", "-", slug)
    return slug

def bloodhorse_search(sire: str) -> Optional[Tuple[str, str]]:
    """
    Query the BloodHorse search endpoint. Return (stallion_id, slug) or None.
    Tries exact string, then slugified variant if needed.
    """
    for query in (sire, slugify_sire(sire)):
        log.debug("  BloodHorse search query = %s", query)
        html = polite_get(SEARCH_URL.format(requests.utils.quote(query)))
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a"):
            href = a.get("href", "")
            m = STALLION_HREF_RE.search(href)
            if m:
                return m.group(1), m.group(2)  # id, slug
        # no match—next strategy
    return None

# ---------------------------------------------------------------------------
# PAGE SCRAPE
# ---------------------------------------------------------------------------
def scrape_page_for_fees(html: str) -> Dict[int, int]:
    """Return {stud_fee_year: fee_usd} from a single auctions page."""
    fees: Dict[int, int] = {}
    for m in STUD_FEE_RE.finditer(html):
        year = int(m.group(1))
        fee = int(m.group(2).replace(",", ""))
        fees[year] = fee
    return fees

def harvest_fees_for_sire(stallion_id: str, slug: str) -> List[Tuple[int, int]]:
    """Crawl all YEARS_TO_CRAWL; return sorted list of (year, fee)."""
    seen: Dict[int, int] = {}
    for sales_year in YEARS_TO_CRAWL:
        url = (
            f"https://www.bloodhorse.com/stallion-register/stallions/"
            f"{stallion_id}/{slug}/auctions/{sales_year}"
        )
        html = polite_get(url)
        if not html:
            continue
        if "Weanlings" not in html:
            log.debug("    %s: no Weanlings section", sales_year)
            continue
        page_fees = scrape_page_for_fees(html)
        for y, fee in page_fees.items():
            if y not in seen:
                seen[y] = fee
        time.sleep(random.uniform(1.0, 2.0))
    return sorted(seen.items())

# ---------------------------------------------------------------------------
# FILE IO
# ---------------------------------------------------------------------------
def load_sire_file(path: Path) -> pd.DataFrame:
    """CSV/XLS/XLSX -> DataFrame with Sire,sale_year columns."""
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    elif path.suffix.lower() in {".xls", ".xlsx"}:
        df = pd.read_excel(path, engine="openpyxl")
    else:
        raise ValueError("Input must be .csv, .xls, or .xlsx")
    if set(df.columns) != {"Sire", "sale_year"}:
        raise ValueError("File must contain exactly the columns: Sire, sale_year")
    return df

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="BloodHorse native stud‑fee scraper")
    ap.add_argument("--input",  required=True, help="CSV/XLS/XLSX with Sire,sale_year")
    ap.add_argument("--output", required=True, help="CSV to write stud fees to")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--quiet", action="store_true", help="Only warnings/errors")
    grp.add_argument("--debug", action="store_true", help="Very verbose logging")
    args = ap.parse_args()

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    elif args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    df_sires = load_sire_file(Path(args.input))

    rows: List[Tuple[str, int, int]] = []

    for sire, sale_year in df_sires.itertuples(index=False):
        log.info("▶ Processing %s (%s)…", sire, sale_year)

        lookup = bloodhorse_search(sire)
        if not lookup:
            log.warning("  No BloodHorse record found for %s", sire)
            continue
        stallion_id, slug = lookup
        log.info("  🆔 ID %s  Slug %s", stallion_id, slug)

        fee_pairs = harvest_fees_for_sire(stallion_id, slug)
        if not fee_pairs:
            log.warning("  No stud fees found for %s", sire)
            continue

        for yr, fee in fee_pairs:
            rows.append((sire, yr, fee))
        log.info("  ✓ %d fee years captured", len(fee_pairs))

    out_df = pd.DataFrame(rows, columns=["Sire", "stud_fee_year", "stud_fee_usd"])
    out_df.to_csv(args.output, index=False)
    log.info("✅ Finished. %d total rows written to %s", len(out_df), args.output)


if __name__ == "__main__":
    main()
