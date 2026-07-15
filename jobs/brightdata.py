import os
import time
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


def trigger_scrape(record_limit=100):
    """Kicks off a keyword-discovery scrape, one row per experience level. Returns snapshot_id."""
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
    return resp.json()["snapshot_id"]


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
    """Triggers a scrape, waits for it to complete, and returns the raw result list."""
    snapshot_id = trigger_scrape(record_limit=record_limit)
    wait_for_snapshot(snapshot_id)
    return download_snapshot(snapshot_id)
