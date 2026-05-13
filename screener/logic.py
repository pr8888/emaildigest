import time
from .fmp import fetch_universe, fetch_history, fetch_fundamentals

PCT_THRESHOLD = 30.0   # % above low to qualify
VOL_WARN_RATIO = 0.50  # flag if recent volume < 50% of 3-month avg
MIN_HISTORY_DAYS = 20  # skip stocks with too little data
TRADING_DAYS_3M = 65   # ~3 months of trading days


def run_screen():
    """
    Main entry point. Returns (stocks, clusters).

    stocks   — list of dicts, one per qualifying stock
    clusters — list of dicts grouped by (sector, country), sorted by total desc
    """
    universe = fetch_universe()
    results = []

    for i, stock in enumerate(universe):
        ticker = stock["ticker"]
        exchange = stock["exchange"]

        # Fetch full 370 days so we have both 52-week and 3-month windows
        history = fetch_history(ticker, exchange, days=370)
        if len(history) < MIN_HISTORY_DAYS:
            continue

        # EODHD returns oldest-first; last record = most recent trading day
        current = history[-1]
        price = current.get("close") or 0
        if price <= 0:
            continue

        all_lows = [d["low"] for d in history if d.get("low")]
        if not all_lows:
            continue

        # 52-week low across all fetched data
        year_low = min(all_lows)
        if year_low <= 0:
            continue

        # Quick pre-filter: skip if not even close to qualifying
        if price < year_low * 1.30:
            continue

        # 3-month window = last 65 records (oldest-first, so slice from end)
        recent = history[-TRADING_DAYS_3M:]
        lows_3m = [d["low"] for d in recent if d.get("low")]
        vols_3m = [d["volume"] for d in recent if d.get("volume") is not None]

        if not lows_3m:
            continue

        low_3m = min(lows_3m)
        avg_vol_3m = sum(vols_3m) / len(vols_3m) if vols_3m else 0

        # Recent volume = last 5 trading days
        last5_vols = [d["volume"] for d in history[-5:] if d.get("volume") is not None]
        recent_vol = sum(last5_vols) / len(last5_vols) if last5_vols else 0
        vol_ratio = round(recent_vol / avg_vol_3m, 2) if avg_vol_3m > 0 else 0
        vol_flag = "⚠" if vol_ratio < VOL_WARN_RATIO else ""

        pct_above_52w = round((price - year_low) / year_low * 100, 1)
        pct_above_3m = round((price - low_3m) / low_3m * 100, 1)

        is_recovery = pct_above_52w >= PCT_THRESHOLD
        is_breakout = pct_above_3m >= PCT_THRESHOLD

        if not (is_recovery or is_breakout):
            continue

        if is_recovery and is_breakout:
            signal = "Strong"
        elif is_recovery:
            signal = "Recovery"
        else:
            signal = "Breakout"

        # Only call fundamentals API for stocks that qualified — saves API calls
        fundamentals = fetch_fundamentals(ticker, exchange)

        results.append({
            "symbol": ticker,
            "name": stock["name"],
            "exchange": exchange,
            "country": stock["country"],
            "sector": fundamentals["sector"] or "Unknown",
            "industry": fundamentals["industry"] or "",
            "price": price,
            "year_low": round(year_low, 4),
            "low_3m": round(low_3m, 4),
            "pct_above_52w": pct_above_52w,
            "pct_above_3m": pct_above_3m,
            "vol_ratio": vol_ratio,
            "vol_flag": vol_flag,
            "signal": signal,
        })

        # Pause every 200 stocks to be kind to the API
        if (i + 1) % 200 == 0:
            time.sleep(2)
        else:
            time.sleep(0.1)

    clusters = _build_clusters(results)
    return results, clusters


def _build_clusters(stocks):
    seen = {}
    for s in stocks:
        key = (s["sector"], s["country"])
        if key not in seen:
            seen[key] = {
                "sector": s["sector"],
                "country": s["country"],
                "strong": 0,
                "recovery": 0,
                "breakout": 0,
                "total": 0,
            }
        seen[key][s["signal"].lower()] += 1
        seen[key]["total"] += 1

    return sorted(seen.values(), key=lambda x: x["total"], reverse=True)
