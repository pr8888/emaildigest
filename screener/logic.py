import time
from .fmp import fetch_universe, fetch_history, fetch_sector
from database import get_cached_sector, save_sector_cache

PCT_MIN = 30.0          # % above low to qualify
PCT_MAX = 100.0         # % cap — already-recovered stocks excluded above this
VOL_WARN_RATIO = 0.50   # flag if recent volume < 50% of 3-month avg
MIN_HISTORY_DAYS = 20
TRADING_DAYS_3M = 65    # ~3 months of trading days
MIN_AVG_VOLUME = 50_000 # daily share volume floor (OTC noise filter)
MIN_PRICE = 5.0         # exclude penny stocks
FINNHUB_SLEEP = 1.1     # seconds between uncached Finnhub calls (free plan: 60/min)


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

        history = fetch_history(ticker, exchange, days=370)
        if len(history) < MIN_HISTORY_DAYS:
            continue

        price = history[-1].get("close") or 0
        if price < MIN_PRICE:
            continue

        all_lows = [d["low"] for d in history if d.get("low")]
        if not all_lows:
            continue

        year_low = min(all_lows)
        if year_low <= 0:
            continue

        # Quick pre-filter — saves Finnhub quota and time
        if price < year_low * 1.30:
            continue

        # 3-month window = last 65 records
        recent = history[-TRADING_DAYS_3M:]
        lows_3m = [d["low"] for d in recent if d.get("low")]
        vols_3m = [d["volume"] for d in recent if d.get("volume") is not None]

        if not lows_3m:
            continue

        low_3m = min(lows_3m)
        avg_vol_3m = sum(vols_3m) / len(vols_3m) if vols_3m else 0

        if avg_vol_3m < MIN_AVG_VOLUME:
            continue

        last5_vols = [d["volume"] for d in history[-5:] if d.get("volume") is not None]
        recent_vol = sum(last5_vols) / len(last5_vols) if last5_vols else 0
        vol_ratio = round(recent_vol / avg_vol_3m, 2) if avg_vol_3m > 0 else 0
        vol_flag = "⚠" if vol_ratio < VOL_WARN_RATIO else ""

        pct_above_52w = round((price - year_low) / year_low * 100, 1)
        pct_above_3m = round((price - low_3m) / low_3m * 100, 1)

        in_range_52w = PCT_MIN <= pct_above_52w <= PCT_MAX
        in_range_3m = PCT_MIN <= pct_above_3m <= PCT_MAX

        if not (in_range_52w or in_range_3m):
            continue

        if in_range_52w and in_range_3m:
            signal = "Strong"
        elif in_range_52w:
            signal = "Recovery"
        else:
            signal = "Breakout"

        results.append({
            "symbol": ticker,
            "name": stock["name"],
            "exchange": exchange,
            "country": stock["country"],
            "sector": "",
            "industry": "",
            "price": price,
            "year_low": round(year_low, 4),
            "low_3m": round(low_3m, 4),
            "pct_above_52w": pct_above_52w,
            "pct_above_3m": pct_above_3m,
            "vol_ratio": vol_ratio,
            "vol_flag": vol_flag,
            "signal": signal,
        })

        if (i + 1) % 200 == 0:
            time.sleep(2)
        else:
            time.sleep(0.1)

    _enrich_sectors(results)
    clusters = _build_clusters(results)
    return results, clusters


def _enrich_sectors(stocks):
    """Add sector/industry to each stock dict, using DB cache then Finnhub."""
    for s in stocks:
        cached = get_cached_sector(s["symbol"], s["exchange"])
        if cached is not None:
            s["sector"], s["industry"] = cached
            continue

        sector, industry = fetch_sector(s["symbol"], s["exchange"])
        save_sector_cache(s["symbol"], s["exchange"], sector, industry)
        s["sector"] = sector
        s["industry"] = industry
        time.sleep(FINNHUB_SLEEP)


def _build_clusters(stocks):
    """Group qualifying stocks by (sector, country)."""
    seen = {}
    for s in stocks:
        sector = s["sector"] or "Unknown"
        country = s["country"] or "Unknown"
        key = (sector, country)
        if key not in seen:
            seen[key] = {
                "sector": sector,
                "country": country,
                "strong": 0,
                "recovery": 0,
                "breakout": 0,
                "total": 0,
            }
        seen[key][s["signal"].lower()] += 1
        seen[key]["total"] += 1

    return sorted(seen.values(), key=lambda x: x["total"], reverse=True)
