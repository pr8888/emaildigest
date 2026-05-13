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

COMMON_STOCK_TYPES = {"Common Stock", "common_stock", "stock"}


def _get(path, params=None):
    p = params or {}
    p["api_token"] = os.environ["EODHD_API_KEY"]
    p["fmt"] = "json"
    r = requests.get(f"{BASE}{path}", params=p, timeout=30)
    r.raise_for_status()
    return r.json()


def _is_valid_ticker(ticker, exchange):
    """
    Filter out indices, OTC shells, and foreign listings.
    For US: only standard NYSE/NASDAQ tickers (1-5 uppercase letters, no digits).
    For others: exclude obvious non-stocks (^ prefix, blank).
    """
    if not ticker or ticker.startswith("^"):
        return False
    if exchange == "US":
        return ticker.isalpha() and 1 <= len(ticker) <= 5
    return True


def fetch_universe():
    """
    Returns common stocks across all exchanges.
    Pre-filtered by ticker format — no bulk price call needed.
    Price filtering happens in logic.py after history is fetched.
    """
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
                all_stocks.append({
                    "ticker": ticker,
                    "exchange": exchange,
                    "name": s.get("Name") or "",
                    "country": s.get("Country") or "",
                })
            time.sleep(0.3)
        except Exception:
            continue
    return all_stocks


def fetch_history(ticker, exchange, days=370):
    """
    Return EOD history for the last N calendar days, oldest-first.
    Each record: {date, open, high, low, close, adjusted_close, volume}
    """
    from_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        data = _get(f"/eod/{ticker}.{exchange}", {"from": from_date})
        return data if isinstance(data, list) else []
    except Exception:
        return []
