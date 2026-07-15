import re
from datetime import date

HEADER_BG = "#1a1a2e"
FO_COLOR = "#1a7f37"
PM_COLOR = "#0550ae"


def _style_description(desc_html):
    """Inline-style the raw <p>/<strong>/<ul>/<li>/<em> fragment for email clients."""
    desc_html = re.sub(r"<p>", '<p style="margin:0 0 8px;font-size:13px;color:#333;line-height:1.55">', desc_html)
    desc_html = re.sub(
        r"<strong>", '<strong style="display:block;font-size:13px;color:#1a1a2e;margin-top:10px">', desc_html
    )
    desc_html = re.sub(r"<em>", '<em style="font-style:normal;color:#666">', desc_html)
    desc_html = re.sub(r"<ul>", '<ul style="margin:0 0 8px;padding-left:20px">', desc_html)
    desc_html = re.sub(
        r"<li>", '<li style="font-size:13px;color:#333;line-height:1.5;margin-bottom:4px">', desc_html
    )
    return desc_html


def _job_card(job):
    tag = ""
    if job["score"] >= 2:
        tag = f'<span style="background:{FO_COLOR};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600">Family Office</span>'
    elif job["score"] == 1:
        tag = f'<span style="background:{PM_COLOR};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600">Public Markets</span>'

    posted = (job.get("job_posted_date") or "")[:10]

    return f"""
    <div style="background:#fff;border-radius:10px;padding:18px 20px;margin-bottom:14px;box-shadow:0 1px 4px rgba(0,0,0,0.06)">
      <div>
        <a href="{job['url']}" target="_blank" style="font-size:16px;font-weight:600;color:#3a5bd9;text-decoration:underline">{job['job_title']}</a>
        {f'&nbsp;{tag}' if tag else ''}
      </div>
      <div style="font-size:13px;color:#777;margin-top:4px">{job['company_name']} &middot; {job['job_location']} &middot; posted {posted}</div>
      <div style="margin-top:12px;padding-top:12px;border-top:1px solid #eee">
        {_style_description(job['description_html'])}
      </div>
      <a href="{job['url']}" target="_blank" style="font-size:12px;font-weight:600;color:#3a5bd9;text-decoration:underline;margin-top:6px;display:inline-block">View full posting on LinkedIn &rarr;</a>
    </div>"""


def build_jobs_email(jobs, run_date=None):
    """Returns (html, plain) tuple for the weekly investment jobs email."""
    if run_date is None:
        run_date = date.today().strftime("%b %d, %Y")

    fo_count = sum(1 for j in jobs if j["score"] >= 2)
    pm_count = sum(1 for j in jobs if j["score"] == 1)

    cards = "".join(_job_card(j) for j in jobs) if jobs else \
        "<div style='color:#888;padding:12px'>No matching roles this week.</div>"

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f3fa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="max-width:820px;margin:32px auto;padding:0 16px">

  <div style="background:{HEADER_BG};border-radius:12px 12px 0 0;padding:28px 36px">
    <div style="font-size:11px;letter-spacing:2px;color:#8899bb;text-transform:uppercase;margin-bottom:6px">Weekly Investment Jobs — Singapore</div>
    <div style="font-size:24px;font-weight:700;color:#fff;font-family:Georgia,serif">{run_date}</div>
    <div style="font-size:14px;color:#aab;margin-top:6px">{len(jobs)} roles &bull; {fo_count} family office &bull; {pm_count} public markets</div>
  </div>

  <div style="background:#fff;padding:18px 36px;border-bottom:1px solid #eee;font-size:12px;color:#888">
    Filters: keyword "investments" &middot; Mid-Senior/Director/Executive &middot; 8+ yrs (if stated) &middot;
    no banks/private banks, PE/VC, real estate, or pod shops &middot; English only
  </div>

  <div style="background:#f0f3fa;padding:24px 36px 4px">
    {cards}
  </div>

  <div style="text-align:center;padding:24px;color:#bbb;font-size:12px;background:#fff;border-radius:0 0 12px 12px">
    farrer36.com &bull; Weekly Investment Jobs &bull; Source: LinkedIn via Bright Data
  </div>

</div>
</body>
</html>"""

    plain_lines = [f"WEEKLY INVESTMENT JOBS — SINGAPORE — {run_date}", "=" * 60,
                    f"{len(jobs)} roles ({fo_count} family office, {pm_count} public markets)", ""]
    for j in jobs:
        plain_lines += [
            j["job_title"], f"  {j['company_name']} | {j['job_location']}", f"  {j['url']}", ""
        ]
    if not jobs:
        plain_lines.append("No matching roles this week.")
    plain = "\n".join(plain_lines)

    return html, plain
