import time
from .fmp import fetch_universe, fetch_history

PCT_THRESHOLD = 30.0   # % above low to qualify
VOL_WARN_RATIO = 0.50  # flag if recent volume < 50% of 3-month avg (unusually quiet)
MIN_HISTORY_DAYS = 20  # skip stocks with fewer data points than this


def run_screen():
    """
    Main entry point. Returns (stocks, clusters).

    stocks  — list of dicts, one per qualifying stock
    clusters — list of dicts grouped by (sector, country), sorted by total desc
    """
    raw_candidates = fetch_universe()
    results = []

    for i, s in enumerate(raw_candidates):
        symbol = s.get("symbol", "")
        if not symbol:
            continue

        history = fetch_history(symbol, days=65)
        if len(history) < MIN_HISTORY_DAYS:
            continue

        price = s.get("price") or 0
        year_low = s.get("yearLow") or 0

        if price <= 0 or year_low <= 0:
            continue

        lows = [d["low"] for d in history if d.get("low")]
        volumes = [d["volume"] for d in history if d.get("volume") is not None]

        if not lows or not volumes:
            continue

        low_3m = min(lows)
        avg_vol_3m = sum(volumes) / len(volumes)
        # history is newest-first; take last 5 entries for recent volume
        recent_vol = sum(volumes[:5]) / min(5, len(volumes))
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

        results.append({
            "symbol": symbol,
            "name": s.get("companyName") or "",
            "exchange": s.get("exchangeShortName") or "",
            "country": s.get("country") or "",
            "sector": s.get("sector") or "Unknown",
            "industry": s.get("industry") or "",
            "price": price,
            "year_low": year_low,
            "low_3m": round(low_3m, 4),
            "pct_above_52w": pct_above_52w,
            "pct_above_3m": pct_above_3m,
            "vol_ratio": vol_ratio,
            "vol_flag": vol_flag,
            "signal": signal,
        })

        # Gentle rate limiting: pause briefly every 200 stocks
        if (i + 1) % 200 == 0:
            time.sleep(2)
        else:
            time.sleep(0.25)

    clusters = _build_clusters(results)
    return results, clusters


def _build_clusters(stocks):
    """
    Group qualifying stocks by (sector, country).
    Returns list of cluster dicts sorted by total count descending.
    Delta vs last week is filled in by the database layer before saving.
    """
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
