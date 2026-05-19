import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from .fmp import fetch_universe, fetch_history, fetch_sector
from database import get_cached_sector, save_sector_cache

PCT_MIN = 30.0          # % above low to qualify
PCT_MAX = 100.0         # % cap — already-recovered stocks excluded above this
VOL_WARN_RATIO = 0.50   # flag if recent volume < 50% of 3-month avg
MIN_HISTORY_DAYS = 20
TRADING_DAYS_3M = 65    # ~3 months of trading days
MIN_AVG_VOLUME = 50_000 # daily share volume floor
MIN_PRICE = 5.0         # exclude penny stocks
FINNHUB_SLEEP = 1.1     # seconds between uncached Finnhub calls (60/min limit)
MAX_WORKERS = 8         # concurrent EODHD history calls
WORKER_SLEEP = 0.3      # per-worker delay to stay well within rate limits


def run_screen():
    """
    Main entry point. Returns (stocks, clusters).

    Uses a thread pool to fetch history for multiple stocks concurrently,
    cutting total runtime from ~90 min (single-thread) to ~30 min.
    """
    universe = fetch_universe()
    print(f"SCREENER: universe = {len(universe)} stocks across all exchanges")

    results = []
    done = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_check_stock, s): s for s in universe}
        for future in as_completed(futures):
            done += 1
            try:
                r = future.result()
                if r:
                    results.append(r)
            except Exception:
                pass
            if done % 1000 == 0:
                print(f"SCREENER: {done}/{len(universe)} checked, {len(results)} qualifying so far")

    print(f"SCREENER: scan complete — {len(results)} qualifying stocks, enriching sectors...")
    _enrich_sectors(results)
    clusters = _build_clusters(results)
    return results, clusters


def _check_stock(stock):
    """
    Worker function: fetch 370-day history for one stock and return a
    qualifying result dict, or None if it doesn't pass all filters.
    """
    time.sleep(WORKER_SLEEP)

    ticker = stock["ticker"]
    exchange = stock["exchange"]

    history = fetch_history(ticker, exchange, days=370)
    if len(history) < MIN_HISTORY_DAYS:
        return None

    price = history[-1].get("close") or 0
    if price < MIN_PRICE:
        return None

    all_lows = [d["low"] for d in history if d.get("low")]
    if not all_lows:
        return None

    year_low = min(all_lows)
    if year_low <= 0:
        return None

    if price < year_low * 1.30:
        return None

    recent = history[-TRADING_DAYS_3M:]
    lows_3m = [d["low"] for d in recent if d.get("low")]
    vols_3m = [d["volume"] for d in recent if d.get("volume") is not None]

    if not lows_3m:
        return None

    low_3m = min(lows_3m)
    avg_vol_3m = sum(vols_3m) / len(vols_3m) if vols_3m else 0

    if avg_vol_3m < MIN_AVG_VOLUME:
        return None

    last5_vols = [d["volume"] for d in history[-5:] if d.get("volume") is not None]
    recent_vol = sum(last5_vols) / len(last5_vols) if last5_vols else 0
    vol_ratio = round(recent_vol / avg_vol_3m, 2) if avg_vol_3m > 0 else 0
    vol_flag = "⚠" if vol_ratio < VOL_WARN_RATIO else ""

    pct_above_52w = round((price - year_low) / year_low * 100, 1)
    pct_above_3m = round((price - low_3m) / low_3m * 100, 1)

    in_range_52w = PCT_MIN <= pct_above_52w <= PCT_MAX
    in_range_3m = PCT_MIN <= pct_above_3m <= PCT_MAX

    if not (in_range_52w or in_range_3m):
        return None

    if in_range_52w and in_range_3m:
        signal = "Strong"
    elif in_range_52w:
        signal = "Recovery"
    else:
        signal = "Breakout"

    return {
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
    }


def _enrich_sectors(stocks):
    """Add sector/industry to each stock dict, using DB cache then Finnhub."""
    uncached = 0
    for s in stocks:
        cached = get_cached_sector(s["symbol"], s["exchange"])
        if cached is not None:
            s["sector"], s["industry"] = cached
            continue

        sector, industry = fetch_sector(s["symbol"], s["exchange"])
        save_sector_cache(s["symbol"], s["exchange"], sector, industry)
        s["sector"] = sector
        s["industry"] = industry
        uncached += 1
        time.sleep(FINNHUB_SLEEP)

    print(f"SCREENER: sector enrichment done ({uncached} new Finnhub lookups)")


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
