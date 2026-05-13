import os
import time
import requests
from datetime import datetime, timedelta

BASE = "https://eodhd.com/api"

# EODHD exchange codes for IBKR-tradeable markets.
# Verify against https://eodhd.com/financial-apis/stock-market-list/ if any return empty.
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
    "SA",    # Brazil (B3/São Paulo)
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


def fetch_universe():
    """
    Returns list of stock dicts for all common stocks across target exchanges.
    Each dict has: ticker, exchange, name, country.
    """
    all_stocks = []
    for exchange in EXCHANGES:
        try:
            symbols = _get(f"/exchange-symbol-list/{exchange}")
            if not isinstance(symbols, list):
                continue
            for s in symbols:
                if s.get("Type") in COMMON_STOCK_TYPES:
                    all_stocks.append({
                        "ticker": s["Code"],
                        "exchange": exchange,
                        "name": s.get("Name") or "",
                        "country": s.get("Country") or "",
                    })
            time.sleep(0.2)
        except Exception:
            continue
    return all_stocks


def fetch_history(ticker, exchange, days=370):
    """
    Return EOD history for the last N calendar days.
    EODHD returns data oldest-first.
    Each record: {date, open, high, low, close, adjusted_close, volume}
    """
    from_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        data = _get(f"/eod/{ticker}.{exchange}", {"from": from_date})
        return data if isinstance(data, list) else []
    except Exception:
        return []


def fetch_fundamentals(ticker, exchange):
    """Return sector and industry for a qualifying stock."""
    try:
        data = _get(f"/fundamentals/{ticker}.{exchange}", {"filter": "General"})
        if isinstance(data, dict):
            return {
                "sector": data.get("Sector") or "",
                "industry": data.get("Industry") or "",
            }
    except Exception:
        pass
    return {"sector": "", "industry": ""}
