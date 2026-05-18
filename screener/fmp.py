import os
import time
import requests
from datetime import datetime, timedelta

BASE = "https://eodhd.com/api"

EXCHANGES = [
    "US",    # NYSE / NASDAQ / AMEX
    "TO",    # Canada (Toronto)
    "LSE",   # UK (London)
    "XETRA", # Germany
    "PA",    # France (Paris)
    "AS",    # Netherlands (Amsterdam)
    "SW",    # Switzerland
    "ST",    # Sweden (Stockholm)
    "T",     # Japan (Tokyo)
    "HK",    # Hong Kong
    "AU",    # Australia (ASX)
    "SI",    # Singapore
    "KO",    # South Korea
    "SA",    # Brazil (B3)
    "MX",    # Mexico
]

# Fallback country names when EODHD returns blank
EXCHANGE_COUNTRIES = {
    "US": "USA", "TO": "Canada", "LSE": "UK", "XETRA": "Germany",
    "PA": "France", "AS": "Netherlands", "SW": "Switzerland", "ST": "Sweden",
    "T": "Japan", "HK": "Hong Kong", "AU": "Australia", "SI": "Singapore",
    "KO": "South Korea", "SA": "Brazil", "MX": "Mexico",
}

# EODHD exchange code → Finnhub symbol suffix
FINNHUB_SUFFIX = {
    "US": "",    "TO": ".TO",  "LSE": ".L",   "XETRA": ".DE",
    "PA": ".PA", "AS": ".AS",  "SW": ".SW",   "ST": ".ST",
    "T": ".T",   "HK": ".HK", "AU": ".AX",   "SI": ".SI",
    "KO": ".KS", "SA": ".SA", "MX": ".MX",
}

COMMON_STOCK_TYPES = {"Common Stock", "common_stock", "stock"}


def _get(path, params=None):
    p = params or {}
    p["api_token"] = os.environ["EODHD_API_KEY"]
    p["fmt"] = "json"
    r = requests.get(f"{BASE}{path}", params=p, timeout=30)
    r.raise_for_status()
    return r.json()


def _is_valid_ticker(ticker, exchange):
    if not ticker or ticker.startswith("^"):
        return False
    if exchange == "US":
        return ticker.isalpha() and 1 <= len(ticker) <= 5
    return True


def fetch_universe():
    all_stocks = []
    for exchange in EXCHANGES:
        try:
            symbols = _get(f"/exchange-symbol-list/{exchange}")
            if not isinstance(symbols, list):
                continue
            for s in symbols:
                if s.get("Type") not in COMMON_STOCK_TYPES:
                    continue
                ticker = s.get("Code", "")
                if not _is_valid_ticker(ticker, exchange):
                    continue
                country = s.get("Country") or EXCHANGE_COUNTRIES.get(exchange, "")
                all_stocks.append({
                    "ticker": ticker,
                    "exchange": exchange,
                    "name": s.get("Name") or "",
                    "country": country,
                })
            time.sleep(0.3)
        except Exception:
            continue
    return all_stocks


def fetch_history(ticker, exchange, days=370):
    from_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        data = _get(f"/eod/{ticker}.{exchange}", {"from": from_date})
        return data if isinstance(data, list) else []
    except Exception:
        return []


def fetch_sector(ticker, exchange):
    """Fetch sector from Finnhub. Returns (sector, industry)."""
    key = os.environ.get("FINNHUB_API_KEY", "")
    if not key:
        return "", ""
    suffix = FINNHUB_SUFFIX.get(exchange, "")
    symbol = ticker if exchange == "US" else f"{ticker}{suffix}"
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/stock/profile2",
            params={"symbol": symbol, "token": key},
            timeout=10,
        )
        if not r.ok:
            return "", ""
        data = r.json()
        sector = data.get("finnhubIndustry") or ""
        return sector, sector
    except Exception:
        return "", ""
