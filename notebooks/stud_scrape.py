import re, time, csv, pathlib, requests
from ratelimit import limits, sleep_and_retry
from urllib.parse import quote, quote_plus
from bs4 import BeautifulSoup
from typing import Optional
import pandas as pd
from tqdm import tqdm

# ---------- CONFIG ----------------------------------------------------------
INPUT  = "stud_fee_incomplete.csv"
OUTPUT = "stud_fee_complete.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (stud-fee-bot; +https://github.com/you)"
}
BLOODHORSE_TEMPLATE = (
    "https://www.bloodhorse.com/stallion-register/results?"        # search endpoint
    "SearchType=1&SearchText={name_url}"
)

# optional Paulick (fallback) – the html is messier but sometimes has older fees
PAULICK_TEMPLATE = "https://www.google.com/search?q={name_url}+{year}+stud+fee+PaulickReport"

# seconds between calls to the same host
REQUEST_INTERVAL = 1
# ---------------------------------------------------------------------------


@sleep_and_retry
@limits(calls=1, period=REQUEST_INTERVAL)
def fetch(url):
    """GET a page with polite throttling."""
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.text


def parse_bloodhorse_fee(html: str, year: int) -> Optional[float]:
    """Return stud-fee (USD) if the year appears on the page; else None."""
    soup = BeautifulSoup(html, "html.parser")
    fee_table = soup.find("table", class_="stallion__profile-fees")
    if not fee_table:
        return None

    for row in fee_table.find_all("tr"):
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) != 2:
            continue
        yr, fee = cols
        if yr.isdigit() and int(yr) == year:
            # fees are like '$150,000' or 'Private'
            fee_num = re.sub(r"[^\d.]", "", fee)
            return float(fee_num) if fee_num else None
    return None


def get_fee(sire: str, year: int) -> Optional[float]:
    """Query BloodHorse first; fall back to Paulick/google snippet."""
    url = BLOODHORSE_TEMPLATE.format(name_url=quote(sire))
    try:
        html = fetch(url)
        fee = parse_bloodhorse_fee(html, year)
        if fee:
            return fee
    except Exception:
        pass

    # Fallback quick-and-dirty Google snippet parse (best-effort)
    url = PAULICK_TEMPLATE.format(
        name_url=quote_plus(sire), year=year
    )
    try:
        html = fetch(url)
        snippet_fee = re.search(r"\$(\d[\d,]+)", html)
        if snippet_fee:
            return float(snippet_fee.group(1).replace(",", ""))
    except Exception:
        pass

    return None


def main():
    df = pd.read_csv(INPUT)
    if not {"Sire", "breeding_year"}.issubset(df.columns):
        raise ValueError("CSV must contain 'Sire' and 'breeding_year' columns.")

    fees = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Fetching stud fees"):
        sire = row["Sire"].strip()
        year = int(row["breeding_year"])
        fee = get_fee(sire, year)
        fees.append(fee)

    df["Fee"] = fees
    df.to_csv(OUTPUT, index=False)
    print(f"✅  Wrote {OUTPUT}")
    missing = df["Fee"].isna().sum()
    if missing:
        print(f"⚠️  {missing} rows still missing a fee (no public record found).")

if __name__ == "__main__":
    main()
