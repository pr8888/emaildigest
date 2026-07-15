import os
import time
import json
import requests

BASE_URL = "https://api.brightdata.com/datasets/v3"
DATASET_ID = "gd_lpfll7v5hcqtkxl6l"  # LinkedIn job listings — discover by keyword

EXPERIENCE_LEVELS = ["Mid-Senior level", "Director", "Executive"]

BASE_INPUT = {
    "location": "Singapore",
    "keyword": "investments",
    "country": "SG",
    "time_range": "Past week",
    "job_type": "Full-time",
    "remote": "On-site",
}

POLL_INTERVAL_SECONDS = 20
MAX_WAIT_SECONDS = 25 * 60  # snapshots for ~300 records took several minutes in manual testing


def _headers():
    return {
        "Authorization": f"Bearer {os.environ['BRIGHTDATA_API_KEY']}",
        "Content-Type": "application/json",
    }


def _parse_ndjson(text):
    records = []
    for line in text.strip().splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def trigger_scrape(record_limit=100):
    """
    Kicks off a keyword-discovery scrape, one row per experience level.

    Bright Data sometimes finishes fast enough to return the actual results
    inline (as newline-delimited JSON), and sometimes returns a snapshot_id
    to poll instead. Returns either ("data", [records]) or ("snapshot", id).
    """
    payload = {
        "input": [
            {**BASE_INPUT, "experience_level": level} for level in EXPERIENCE_LEVELS
        ],
        "limit_per_input": record_limit,
    }
    params = {
        "dataset_id": DATASET_ID,
        "notify": "false",
        "include_errors": "true",
        "type": "discover_new",
        "discover_by": "keyword",
    }
    resp = requests.post(f"{BASE_URL}/scrape", headers=_headers(), params=params, json=payload, timeout=60)
    resp.raise_for_status()

    try:
        parsed = resp.json()
    except json.JSONDecodeError:
        return ("data", _parse_ndjson(resp.text))

    if isinstance(parsed, list):
        return ("data", parsed)
    if isinstance(parsed, dict) and "snapshot_id" in parsed:
        return ("snapshot", parsed["snapshot_id"])
    raise RuntimeError(f"Unexpected Bright Data response shape: {resp.text[:500]}")


def wait_for_snapshot(snapshot_id):
    """Polls progress until status is 'ready' or 'failed', or MAX_WAIT_SECONDS elapses."""
    elapsed = 0
    while elapsed < MAX_WAIT_SECONDS:
        resp = requests.get(f"{BASE_URL}/progress/{snapshot_id}", headers=_headers(), timeout=30)
        resp.raise_for_status()
        status = resp.json().get("status")
        if status == "ready":
            return
        if status == "failed":
            raise RuntimeError(f"Bright Data snapshot {snapshot_id} failed")
        time.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS
    raise TimeoutError(f"Bright Data snapshot {snapshot_id} not ready after {MAX_WAIT_SECONDS}s")


def download_snapshot(snapshot_id):
    resp = requests.get(
        f"{BASE_URL}/snapshot/{snapshot_id}", headers=_headers(),
        params={"format": "json"}, timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def fetch_jobs(record_limit=100):
    """Triggers a scrape and returns the raw result list, polling a snapshot if needed."""
    kind, value = trigger_scrape(record_limit=record_limit)
    if kind == "data":
        return value
    wait_for_snapshot(value)
    return download_snapshot(value)
