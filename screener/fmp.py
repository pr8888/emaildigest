import os
import time
import requests

BASE = "https://financialmodelingprep.com/api"

# IBKR-tradeable exchanges using FMP's exchangeShortName values.
# Verify against https://financialmodelingprep.com/developer/docs#exchanges-list if any return no data.
EXCHANGES = [
    # Americas
    "NYSE", "NASDAQ", "AMEX",
    "TSX",     # Canada
    "BVMF",    # Brazil (B3)
    "BMV",     # Mexico
    # Europe
    "LSE",     # UK
    "XETRA",   # Germany
    "EURONEXT",# France / Netherlands / Belgium
    "SWX",     # Switzerland
    "STO",     # Sweden
    # Asia-Pacific
    "TSE",     # Japan
    "HKSE",    # Hong Kong
    "ASX",     # Australia
    "SGX",     # Singapore
    "KSE",     # South Korea
]

MIN_MARKET_CAP = 50_000_000  # USD — excludes micro/nano caps


def _get(path, params=None):
    p = params or {}
    p["apikey"] = os.environ["FMP_API_KEY"]
    r = requests.get(f"{BASE}{path}", params=p, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_universe():
    """
    Pull all non-ETF, actively-traded stocks from target exchanges.
    Pre-filters to price >= 1.30 * yearLow so we only fetch history
    for stocks that could qualify for either signal.
    """
    candidates = []
    for exchange in EXCHANGES:
        offset = 0
        while True:
            try:
                batch = _get("/v3/stock-screener", {
                    "exchange": exchange,
                    "marketCapMoreThan": MIN_MARKET_CAP,
                    "isActivelyTrading": "true",
                    "isEtf": "false",
                    "limit": 250,
                    "offset": offset,
                })
            except Exception:
                break

            if not batch:
                break

            for s in batch:
                price = s.get("price") or 0
                year_low = s.get("yearLow") or 0
                if price > 0 and year_low > 0 and price >= year_low * 1.30:
                    candidates.append(s)

            if len(batch) < 250:
                break
            offset += 250
            time.sleep(0.25)

    return candidates


def fetch_history(symbol, days=65):
    """Return up to N daily OHLCV records (newest first) for a symbol."""
    try:
        data = _get(f"/v3/historical-price-full/{symbol}", {"timeseries": days})
        return data.get("historical", [])
    except Exception:
        return []
