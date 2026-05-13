from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import os

load_dotenv()

from database import (
    init_db, save_article, get_weekly_articles, save_digest, save_feedback,
    get_feedback_history, get_article_count, get_queued_articles,
    save_screener_run, save_screener_stocks, save_screener_clusters, get_latest_screener_results,
)
from claude import summarize_article, compose_digest
from email_utils import parse_inbound_email, send_digest_email

scheduler = BackgroundScheduler()
APP_URL = os.environ.get("APP_URL", "http://localhost:8000")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Saturday 8am SGT = Saturday 00:00 UTC
    scheduler.add_job(
        run_weekly_digest,
        CronTrigger(day_of_week="sat", hour=0, minute=0, timezone="UTC"),
    )
    # Sunday 00:00 UTC = Sunday 8:00 AM SGT
    scheduler.add_job(
        run_weekly_screener,
        CronTrigger(day_of_week="sun", hour=0, minute=0, timezone="UTC"),
    )
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)


@app.post("/inbound")
async def inbound_email(request: Request, background_tasks: BackgroundTasks):
    """Receives forwarded emails from SendGrid Inbound Parse."""
    form_data = await request.form()
    article = parse_inbound_email(form_data)
    if article:
        background_tasks.add_task(process_article, article)
    return {"status": "ok"}


def _is_priority_sender(sender: str) -> bool:
    """Check if sender matches any name in the PRIORITY_SENDERS env var."""
    priority_list = os.environ.get("PRIORITY_SENDERS", "")
    if not priority_list:
        return False
    sender_lower = sender.lower()
    return any(p.strip().lower() in sender_lower for p in priority_list.split(",") if p.strip())


def process_article(article: dict):
    summary, tags, must_read_score, is_paywalled = summarize_article(article["text"], article["subject"])

    # Priority senders always score at least 0.85
    if _is_priority_sender(article["sender"]):
        must_read_score = max(must_read_score, 0.85)

    save_article(
        subject=article["subject"],
        sender=article["sender"],
        raw_content=article["text"],
        summary=summary,
        tags=tags,
        must_read_score=must_read_score,
        is_paywalled=is_paywalled,
    )


@app.post("/send-digest")
async def trigger_digest():
    """Manual trigger — use this to test without waiting for Saturday."""
    run_weekly_digest()
    return {"status": "digest sent"}


def run_weekly_digest():
    articles = get_weekly_articles()
    if not articles:
        return

    article_ids = [a.id for a in articles]
    week_start = datetime.now(timezone.utc) - timedelta(days=7)
    digest_id = save_digest(article_ids=article_ids, week_start=week_start)

    feedback_history = get_feedback_history(weeks=8)
    html, plain = compose_digest(articles, feedback_history, digest_id=digest_id, app_url=APP_URL, is_priority_sender=_is_priority_sender)

    from datetime import date
    week_str = date.today().strftime("%b %d, %Y")
    send_digest_email(html, plain, subject=f"Your Weekly Markets Digest — {week_str}")


@app.get("/feedback")
async def feedback(digest_id: int, type: str, value: str):
    """Called when Pratyush clicks a feedback button in the digest email."""
    save_feedback(digest_id=digest_id, type=type, value=value)

    messages = {
        "short": "Got it — we'll aim for more depth next week.",
        "good": "Great — keeping the same length going forward.",
        "long": "Got it — we'll trim it down next week.",
    }
    msg = messages.get(value, f"Thanks — rated {value} stars this week.")

    return HTMLResponse(f"""<!DOCTYPE html>
<html><body style="font-family:sans-serif;text-align:center;padding:80px 20px;background:#f0f3fa">
  <div style="max-width:400px;margin:0 auto;background:#fff;border-radius:12px;padding:48px;box-shadow:0 2px 12px rgba(0,0,0,0.08)">
    <div style="font-size:48px;margin-bottom:16px;color:#3a5bd9">&#10003;</div>
    <h2 style="color:#1a1a2e;margin:0 0 12px;font-family:Georgia,serif">Feedback received</h2>
    <p style="color:#666;line-height:1.6;font-size:15px">{msg}</p>
    <p style="color:#bbb;font-size:12px;margin-top:24px">You can close this tab.</p>
  </div>
</body></html>""")


@app.get("/admin")
async def admin_page():
    """Simple browser-based test panel."""
    password = os.environ.get("ADMIN_PASSWORD", "changeme")
    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Digest Admin</title></head>
<body style="font-family:sans-serif;background:#f0f3fa;padding:40px 20px">
  <div style="max-width:680px;margin:0 auto">
    <div style="background:#fff;border-radius:12px;padding:40px;box-shadow:0 2px 12px rgba(0,0,0,0.09);margin-bottom:24px;text-align:center">
      <h2 style="color:#1a1a2e;margin:0 0 8px">Digest Admin</h2>
      <p style="color:#888;font-size:13px;margin:0 0 32px">farrer36.com &bull; Weekly Markets Digest</p>

      <div id="auth">
        <input id="pw" type="password" placeholder="Password" style="width:100%;padding:10px 14px;border:1px solid #d0d9f0;border-radius:8px;font-size:14px;box-sizing:border-box;margin-bottom:12px">
        <button onclick="unlock()" style="width:100%;padding:11px;background:#3a5bd9;color:#fff;border:none;border-radius:8px;font-size:14px;cursor:pointer">Unlock</button>
      </div>

      <div id="panel" style="display:none">
        <div id="count" style="background:#f0f3fa;border-radius:8px;padding:16px;margin-bottom:16px;font-size:14px;color:#333">Loading...</div>
        <button onclick="sendDigest()" style="width:100%;padding:14px;background:#3a5bd9;color:#fff;border:none;border-radius:8px;font-size:15px;cursor:pointer;margin-bottom:12px">
          Send Digest Now
        </button>
        <p id="status" style="color:#666;font-size:13px;min-height:20px"></p>
      </div>
    </div>

    <div id="article-list" style="display:none">
      <h3 style="color:#1a1a2e;font-size:15px;margin:0 0 12px">Articles Queued for Next Digest</h3>
      <div id="articles"></div>
    </div>
  </div>

  <script>
    const CORRECT = "{password}";
    async function unlock() {{
      if (document.getElementById("pw").value === CORRECT) {{
        document.getElementById("auth").style.display = "none";
        document.getElementById("panel").style.display = "block";
        loadCount();
        loadArticles();
      }} else {{
        alert("Wrong password");
      }}
    }}
    async function loadCount() {{
      const res = await fetch("/article-count");
      const data = await res.json();
      document.getElementById("count").innerHTML = `<strong>${{data.this_week}}</strong> articles queued for this Saturday &bull; <strong>${{data.total}}</strong> total all time`;
    }}
    async function loadArticles() {{
      const res = await fetch("/queued-articles");
      const articles = await res.json();
      document.getElementById("article-list").style.display = "block";
      const container = document.getElementById("articles");
      if (!articles.length) {{
        container.innerHTML = '<p style="color:#888;font-size:14px">No articles queued yet.</p>';
        return;
      }}
      container.innerHTML = articles.map(a => {{
        const score = (a.must_read_score * 100).toFixed(0);
        const scoreColor = a.must_read_score >= 0.7 ? "#2e7d32" : a.must_read_score >= 0.4 ? "#e65100" : "#999";
        const date = a.received_at ? new Date(a.received_at).toLocaleDateString("en-SG", {{day:"numeric",month:"short",hour:"2-digit",minute:"2-digit",timeZone:"Asia/Singapore"}}) : "";
        const tags = (a.tags || []).map(t => `<span style="background:#e8f0fe;color:#3a5bd9;padding:2px 8px;border-radius:10px;font-size:11px;margin-right:4px">${{t}}</span>`).join("");
        const paywalled = a.is_paywalled ? '<span style="background:#fff3e0;color:#e65100;padding:2px 8px;border-radius:10px;font-size:11px;margin-right:4px">Paywalled</span>' : "";
        return `<div style="background:#fff;border-radius:10px;padding:16px 20px;margin-bottom:10px;box-shadow:0 1px 4px rgba(0,0,0,0.07);text-align:left">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">
            <div style="flex:1;min-width:0">
              <div style="font-size:14px;font-weight:600;color:#1a1a2e;margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${{a.subject}}</div>
              <div style="font-size:12px;color:#888;margin-bottom:6px">${{a.sender}} &bull; ${{date}} SGT</div>
              <div>${{paywalled}}${{tags}}</div>
            </div>
            <div style="font-size:20px;font-weight:700;color:${{scoreColor}};white-space:nowrap">${{score}}<span style="font-size:11px;font-weight:400;color:#aaa">/100</span></div>
          </div>
        </div>`;
      }}).join("");
    }}
    async function sendDigest() {{
      document.getElementById("status").textContent = "Sending...";
      const res = await fetch("/send-digest", {{method: "POST"}});
      const data = await res.json();
      document.getElementById("status").textContent = data.status === "digest sent"
        ? "Done! Check your inbox."
        : "No articles found for this week yet.";
    }}
  </script>
</body></html>""")


@app.get("/article-count")
async def article_count():
    total, this_week = get_article_count()
    return {"total": total, "this_week": this_week}


@app.get("/queued-articles")
async def queued_articles():
    return get_queued_articles()


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Screener ─────────────────────────────────────────────────────────────────

def run_weekly_screener():
    from screener.logic import run_screen
    from screener.report import build_screener_email

    stocks, clusters = run_screen()
    if not stocks:
        return

    run_id = save_screener_run(stock_count=len(stocks), cluster_count=len(clusters))
    save_screener_stocks(run_id, stocks)
    save_screener_clusters(run_id, clusters)

    # Re-fetch clusters with delta populated from DB
    _, clusters_with_delta = get_latest_screener_results()

    html, plain = build_screener_email(clusters_with_delta, stocks)
    week_str = datetime.now(timezone.utc).strftime("%b %d, %Y")
    from email_utils import send_digest_email
    send_digest_email(html, plain, subject=f"Weekly Stock Screen — {week_str}")


@app.post("/screener/send")
async def trigger_screener(background_tasks: BackgroundTasks):
    """Manual trigger for the weekly stock screener."""
    background_tasks.add_task(run_weekly_screener)
    return {"status": "screener started — email will arrive in ~10-15 minutes"}


@app.get("/screener/test-eodhd")
async def test_eodhd():
    """Diagnostic: tests EODHD API key, symbol list, and historical price endpoint."""
    import requests
    key = os.environ.get("EODHD_API_KEY", "NOT SET")
    if key == "NOT SET":
        return {"error": "EODHD_API_KEY not set"}
    try:
        symbol_list = requests.get(
            "https://eodhd.com/api/exchange-symbol-list/US",
            params={"api_token": key, "fmt": "json"},
            timeout=15,
        )
        history = requests.get(
            "https://eodhd.com/api/eod/AAPL.US",
            params={"api_token": key, "fmt": "json", "from": "2026-05-01"},
            timeout=15,
        )
        fundamentals = requests.get(
            "https://eodhd.com/api/fundamentals/AAPL.US",
            params={"api_token": key, "fmt": "json", "filter": "General"},
            timeout=15,
        )
        symbol_data = symbol_list.json() if symbol_list.ok else symbol_list.text[:200]
        # Test yfinance sector lookup
        import yfinance as yf
        aapl_info = yf.Ticker("AAPL").info
        yf_sector = aapl_info.get("sector", "not found")
        yf_industry = aapl_info.get("industryDisp") or aapl_info.get("industry", "not found")

        symbol_data = symbol_list.json() if symbol_list.ok else symbol_list.text[:200]
        return {
            "symbol_list_status": symbol_list.status_code,
            "symbol_list_count": len(symbol_data) if isinstance(symbol_data, list) else "error",
            "history_status": history.status_code,
            "history_sample": history.text[:200],
            "yfinance_sector": yf_sector,
            "yfinance_industry": yf_industry,
        }
    except Exception as e:
        return {"error": str(e)}
