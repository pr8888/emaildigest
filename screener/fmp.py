import os
import time
import requests
from datetime import datetime, timedelta

BASE = "https://eodhd.com/api"

# EODHD exchange codes → Yahoo Finance suffix (for sector/industry lookup)
EXCHANGES = {
    "US":    "",     # NYSE / NASDAQ / AMEX
    "TO":    ".TO",  # Canada (Toronto)
    "LSE":   ".L",   # UK (London)
    "XETRA": ".DE",  # Germany
    "PA":    ".PA",  # France (Paris)
    "AS":    ".AS",  # Netherlands (Amsterdam)
    "SW":    ".SW",  # Switzerland
    "ST":    ".ST",  # Sweden (Stockholm)
    "T":     ".T",   # Japan (Tokyo)
    "HK":    ".HK",  # Hong Kong
    "AU":    ".AX",  # Australia (ASX)
    "SI":    ".SI",  # Singapore
    "KO":    ".KS",  # South Korea
    "SA":    ".SA",  # Brazil (B3)
    "MX":    ".MX",  # Mexico
}

COMMON_STOCK_TYPES = {"Common Stock", "common_stock", "stock"}
MIN_PRICE = 1.0  # exclude sub-$1 stocks (penny stocks, shells, etc.)


def _get(path, params=None):
    p = params or {}
    p["api_token"] = os.environ["EODHD_API_KEY"]
    p["fmt"] = "json"
    r = requests.get(f"{BASE}{path}", params=p, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_bulk_prices(exchange):
    """
    Returns {ticker: last_close_price} for all stocks on the exchange.
    One API call per exchange — used to pre-filter before fetching full history.
    """
    try:
        data = _get(f"/eod/bulk_last_day/{exchange}")
        if not isinstance(data, list):
            return {}
        return {d["code"]: d.get("close") or 0 for d in data}
    except Exception:
        return {}


def fetch_universe():
    """
    Returns list of stock dicts for common stocks across all target exchanges,
    pre-filtered to price > $1 using the bulk EOD endpoint.
    """
    all_stocks = []
    for exchange in EXCHANGES:
        try:
            # Get symbol metadata
            symbols = _get(f"/exchange-symbol-list/{exchange}")
            if not isinstance(symbols, list):
                continue

            # Get current prices in one call (pre-filter)
            bulk_prices = fetch_bulk_prices(exchange)

            for s in symbols:
                if s.get("Type") not in COMMON_STOCK_TYPES:
                    continue
                ticker = s.get("Code", "")
                if not ticker:
                    continue
                price = bulk_prices.get(ticker, 0)
                if price < MIN_PRICE:
                    continue
                all_stocks.append({
                    "ticker": ticker,
                    "exchange": exchange,
                    "name": s.get("Name") or "",
                    "country": s.get("Country") or "",
                    "current_price": price,
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


def fetch_fundamentals(ticker, exchange):
    """
    Return sector and industry via Yahoo Finance (free).
    Only called for stocks that passed the screen.
    """
    try:
        import yfinance as yf
        yahoo_symbol = f"{ticker}{EXCHANGES[exchange]}"
        info = yf.Ticker(yahoo_symbol).info
        return {
            "sector": info.get("sector") or "",
            "industry": info.get("industryDisp") or info.get("industry") or "",
        }
    except Exception:
        return {"sector": "", "industry": ""}
