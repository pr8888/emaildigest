import os
import requests

API_URL = "https://api.brightdata.com/datasets/v3/scrape"
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


def fetch_jobs(record_limit=100):
    """
    Calls Bright Data's LinkedIn Jobs Scraper (discover by keyword) synchronously,
    one row per experience level. Returns the combined raw list of result dicts
    (including any per-row error/mismatch entries — filtering happens in logic.py).
    """
    api_key = os.environ["BRIGHTDATA_API_KEY"]
    payload = {
        "input": [
            {**BASE_INPUT, "experience_level": level} for level in EXPERIENCE_LEVELS
        ],
        "limit_per_input": record_limit,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    params = {
        "dataset_id": DATASET_ID,
        "notify": "false",
        "include_errors": "true",
        "type": "discover_new",
        "discover_by": "keyword",
    }

    resp = requests.post(API_URL, headers=headers, params=params, json=payload, timeout=900)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []
