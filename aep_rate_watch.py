#!/usr/bin/env python3
"""aep_rate_watch.py - poll the Ohio Apples-to-Apples chart for AEP residential
electricity offers and alert when one appears that's meaningfully cheaper than
what you're locked into.

Target:
  https://energychoice.ohio.gov/ApplesToApplesComparision.aspx?Category=Electric&TerritoryId=2&RateCode=1
  (TerritoryId=2 = AEP, RateCode=1 = residential -- verify for your territory.)

The site is ASP.NET WebForms; the offer table is *probably* server-rendered, so
requests + bs4 works. If a raw `curl` of the URL doesn't contain the supplier
rows, the page is JS-rendered -> use Playwright instead.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup


def env_float(name, default):
    v = os.environ.get(name)
    return float(v) if v not in (None, "") else default


def env_int(name, default):
    v = os.environ.get(name)
    return int(v) if v not in (None, "") else default


def env_bool(name, default):
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


# ---------------------------- config ----------------------------
URL = os.environ.get(
    "AEP_URL",
    "https://energychoice.ohio.gov/ApplesToApplesComparision.aspx"
    "?Category=Electric&TerritoryId=2&RateCode=1",
)
STATE_FILE = Path(os.environ.get("RATE_WATCH_STATE", "/data/aep_rate_state.json"))

CURRENT_RATE = env_float("CURRENT_RATE", 0.0998)
MIN_IMPROVEMENT = env_float("MIN_IMPROVEMENT", 0.004)

REQUIRE_FIXED = env_bool("REQUIRE_FIXED", True)
MAX_ETF = env_float("MAX_ETF", 0.0)
MAX_MONTHLY_FEE = env_float("MAX_MONTHLY_FEE", 0.0)
MIN_TERM_MONTHS = env_int("MIN_TERM_MONTHS", 12)
MAX_TERM_MONTHS = env_int("MAX_TERM_MONTHS", 36)

MONTHLY_KWH = env_int("MONTHLY_KWH", 1000)

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")

# 0 = run once and exit; >0 = sleep this many seconds between polls.
POLL_INTERVAL = env_int("POLL_INTERVAL", 0)
# ----------------------------------------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) aep-rate-watch/1.0 (personal use)",
    "Accept": "text/html,application/xhtml+xml",
}

# Column order observed on the live chart:
#   0 checkbox | 1 Supplier | 2 $/kWh | 3 Rate Type | 4 Renew | 5 Intro
#   6 Term | 7 Early Term Fee | 8 Monthly Fee | 9 Promo
COL = dict(supplier=1, rate=2, rate_type=3, term=6, etf=7, fee=8)


def num(s):
    """'$0' / '$150' / '0.0987' / '18 mo.' -> float; junk -> None."""
    if not s:
        return None
    m = re.search(r"-?\d+(\.\d+)?", s.replace(",", ""))
    return float(m.group()) if m else None


def fetch_offers():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    offers = []
    for table in soup.find_all("table"):
        header = " ".join(
            th.get_text(" ", strip=True).lower() for th in table.find_all("th")
        )
        if "kwh" not in header:
            continue
        for row in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in row.find_all("td")]
            if len(cells) <= COL["fee"]:
                continue
            rate = num(cells[COL["rate"]])
            if rate is None or rate > 1.0:
                continue
            etf = num(cells[COL["etf"]])
            fee = num(cells[COL["fee"]])
            offers.append({
                "supplier": cells[COL["supplier"]].split("\n")[0].strip(),
                "rate": rate,
                "fixed": "fixed" in cells[COL["rate_type"]].lower(),
                "term": num(cells[COL["term"]]),
                "etf": etf if etf is not None else 0.0,
                "fee": fee if fee is not None else 0.0,
            })
        if offers:
            break
    return offers


def eligible(o):
    if REQUIRE_FIXED and not o["fixed"]:
        return False
    if o["etf"] > MAX_ETF or o["fee"] > MAX_MONTHLY_FEE:
        return False
    if o["term"] is None or not (MIN_TERM_MONTHS <= o["term"] <= MAX_TERM_MONTHS):
        return False
    return True


def notify(title, body):
    if not NTFY_TOPIC:
        print(f"NOTIFY (no NTFY_TOPIC set): {title}\n{body}", file=sys.stderr)
        return
    try:
        requests.post(
            NTFY_TOPIC,
            data=body.encode("utf-8"),
            headers={"Title": title, "Priority": "high", "Tags": "zap"},
            timeout=15,
        )
    except Exception as e:
        print(f"notify failed: {e}", file=sys.stderr)


def check_once():
    offers = [o for o in fetch_offers() if eligible(o)]
    if not offers:
        print(
            "no eligible offers parsed -- check COL indices / table selector",
            file=sys.stderr,
        )
        return 2

    best = min(offers, key=lambda o: o["rate"])

    prev = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    prev_best = prev.get("best_rate")

    beats_current = best["rate"] <= CURRENT_RATE - MIN_IMPROVEMENT
    is_new = prev_best is None or best["rate"] < prev_best - 1e-9

    if beats_current and is_new:
        saved = (CURRENT_RATE - best["rate"]) * MONTHLY_KWH * 12
        notify(
            f"Cheaper AEP rate: {best['rate']:.4f}/kWh",
            f"{best['supplier']} - {best['rate']:.4f} $/kWh, "
            f"{int(best['term'])} mo, $0 ETF/fee.\n"
            f"You're at {CURRENT_RATE:.4f}. Saves ~${saved:.0f}/yr "
            f"at {MONTHLY_KWH} kWh/mo.",
        )
        print(f"ALERTED: {best['supplier']} {best['rate']:.4f}", flush=True)
    else:
        print(
            f"best={best['rate']:.4f} ({best['supplier']}); no alert "
            f"(need <= {CURRENT_RATE - MIN_IMPROVEMENT:.4f}, prev={prev_best})",
            flush=True,
        )

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({
        "best_rate": best["rate"],
        "best_supplier": best["supplier"],
        "best_term": best["term"],
    }))
    return 0


def main():
    if POLL_INTERVAL <= 0:
        sys.exit(check_once())

    print(f"aep-rate-watch: polling every {POLL_INTERVAL}s", flush=True)
    while True:
        try:
            check_once()
        except Exception as e:
            print(f"check failed: {e}", file=sys.stderr, flush=True)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
