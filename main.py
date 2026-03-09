from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import os

load_dotenv()

from database import init_db, save_article, get_weekly_articles, save_digest, save_feedback, get_feedback_history, get_article_count
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


def process_article(article: dict):
    summary, tags, must_read_score = summarize_article(article["text"], article["subject"])
    save_article(
        subject=article["subject"],
        sender=article["sender"],
        raw_content=article["text"],
        summary=summary,
        tags=tags,
        must_read_score=must_read_score,
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
    html, plain = compose_digest(articles, feedback_history, digest_id=digest_id, app_url=APP_URL)

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
<body style="font-family:sans-serif;background:#f0f3fa;padding:60px 20px;text-align:center">
  <div style="max-width:420px;margin:0 auto;background:#fff;border-radius:12px;padding:48px;box-shadow:0 2px 12px rgba(0,0,0,0.09)">
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

  <script>
    const CORRECT = "{password}";
    async function unlock() {{
      if (document.getElementById("pw").value === CORRECT) {{
        document.getElementById("auth").style.display = "none";
        document.getElementById("panel").style.display = "block";
        const res = await fetch("/article-count");
        const data = await res.json();
        document.getElementById("count").innerHTML = `<strong>${{data.this_week}}</strong> articles queued for this Saturday &bull; <strong>${{data.total}}</strong> total all time`;
      }} else {{
        alert("Wrong password");
      }}
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


@app.get("/health")
async def health():
    return {"status": "ok"}
