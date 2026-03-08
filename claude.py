import anthropic
import json
import os
from collections import Counter

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def summarize_article(text: str, subject: str) -> tuple:
    """Returns (summary, tags, must_read_score)."""
    text = text[:8000]  # Stay well within token limits

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": f"""Summarize this investing article for a busy finance professional focused on equities and macro.

Subject: {subject}

Content:
{text}

Respond with JSON only:
{{
  "summary": "2-3 sentences capturing the key insight and actionable takeaway",
  "tags": ["macro" and/or "equities" and/or "other"],
  "must_read_score": 0.0 to 1.0
}}

Score 0.8-1.0 only for genuinely important macro shifts or high-conviction equity calls. Score 0.3-0.5 for useful but not urgent reads."""
        }]
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if Claude wrapped the JSON
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    result = json.loads(raw.strip())
    return result["summary"], result["tags"], result["must_read_score"]


def compose_digest(articles, feedback_history, digest_id: int, app_url: str) -> tuple:
    """Returns (html, plain_text) for the weekly digest email."""
    sorted_articles = sorted(articles, key=lambda a: a.must_read_score, reverse=True)
    must_reads = sorted_articles[:2]
    rest = sorted_articles[2:]

    # Build feedback context for Claude
    feedback_note = ""
    if feedback_history:
        length_votes = [f.value for f in feedback_history if f.type == "length"]
        if length_votes:
            top = Counter(length_votes).most_common(1)[0][0]
            length_map = {"short": "longer", "good": "the same length", "long": "shorter"}
            feedback_note = f"Based on past feedback, write the digest {length_map.get(top, 'the same length')} than usual."

    # Format articles for Claude
    articles_text = ""
    for i, a in enumerate(sorted_articles):
        articles_text += f"\n[{i+1}] Subject: {a.subject}\nSummary: {a.summary}\nScore: {a.must_read_score:.2f}\nTags: {', '.join(a.tags or [])}\n"

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": f"""Write a weekly investing digest for Pratyush Rastogi, a finance professional in Singapore focused on equities and macro. {feedback_note}

Articles this week (sorted by relevance):
{articles_text}

Adapt the format to however many articles are available this week:
- If 1 article: write a thorough single-article commentary, 8-10 sentences, explaining the key insight and why it matters
- If 2-3 articles: write a "Must Read" section covering all of them with 4-5 sentences each, skip the "Also Worth Reading" section
- If 4+ articles: write all three sections — "Week in Brief" (2 sentences), "Must Read This Week" (top 2, 4-5 sentences each), "Also Worth Reading" (rest, 2 sentences each grouped by macro/equities)

Always write something useful — never refuse or ask for more articles.

Tone: smart analyst friend, not a robot. No bullet points — prose only. Total reading time should be 10-12 minutes."""
        }]
    )

    digest_body = response.content[0].text
    must_read_titles = " & ".join(f'"{a.subject[:45]}..."' for a in must_reads)
    base = f"{app_url}/feedback?digest_id={digest_id}"

    html = _build_html(digest_body, base, must_read_titles)
    plain = digest_body + f"\n\n---\nFeedback — Length: {base}&type=length&value=short (Too Short) | {base}&type=length&value=good (Just Right) | {base}&type=length&value=long (Too Long)"

    return html, plain


def _build_html(body: str, feedback_base: str, must_read_titles: str) -> str:
    paragraphs = ""
    for line in body.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Detect section headers
        clean = line.lstrip("#").replace("**", "").strip()
        if line.startswith("#") or (line.startswith("**") and line.endswith("**")):
            paragraphs += f'<h2 style="color:#1a1a2e;font-size:17px;margin:28px 0 10px;padding-bottom:6px;border-bottom:2px solid #e8f0fe;font-family:sans-serif">{clean}</h2>'
        else:
            paragraphs += f'<p style="margin:0 0 16px;line-height:1.75;color:#2c2c2c">{line}</p>'

    base = feedback_base
    stars = "".join(
        f'<a href="{base}&type=must_read&value={i}" style="display:inline-block;padding:7px 13px;margin:0 3px;background:#fff;border:1px solid #d0d9f0;border-radius:20px;color:#3a5bd9;font-size:13px;text-decoration:none;font-family:sans-serif">{"&#9733;" * i}</a>'
        for i in range(1, 6)
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:20px;background:#f0f3fa;font-family:Georgia,serif">
  <div style="max-width:640px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,0.09)">

    <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);padding:36px 40px;text-align:center">
      <p style="color:#8ba3d4;font-size:11px;letter-spacing:3px;text-transform:uppercase;margin:0 0 8px;font-family:sans-serif">Weekly Digest &bull; Singapore Edition</p>
      <h1 style="color:#fff;font-size:26px;margin:0;font-weight:700">Your Week in Markets</h1>
    </div>

    <div style="padding:36px 40px">
      {paragraphs}
    </div>

    <div style="background:#f8f9fe;border-top:1px solid #e8f0fe;padding:28px 40px">
      <p style="color:#888;font-size:11px;text-transform:uppercase;letter-spacing:2px;margin:0 0 20px;text-align:center;font-family:sans-serif">Quick Feedback</p>

      <p style="font-size:13px;color:#333;margin:0 0 10px;text-align:center;font-family:sans-serif"><strong>How was the length?</strong></p>
      <div style="text-align:center;margin-bottom:24px">
        <a href="{base}&type=length&value=short" style="display:inline-block;padding:8px 18px;margin:0 4px;background:#fff;border:1px solid #d0d9f0;border-radius:20px;color:#3a5bd9;font-size:13px;text-decoration:none;font-family:sans-serif">Too Short</a>
        <a href="{base}&type=length&value=good" style="display:inline-block;padding:8px 18px;margin:0 4px;background:#3a5bd9;border:1px solid #3a5bd9;border-radius:20px;color:#fff;font-size:13px;text-decoration:none;font-family:sans-serif">Just Right</a>
        <a href="{base}&type=length&value=long" style="display:inline-block;padding:8px 18px;margin:0 4px;background:#fff;border:1px solid #d0d9f0;border-radius:20px;color:#3a5bd9;font-size:13px;text-decoration:none;font-family:sans-serif">Too Long</a>
      </div>

      <p style="font-size:13px;color:#333;margin:0 0 6px;text-align:center;font-family:sans-serif"><strong>Rate this week's must reads:</strong></p>
      <p style="font-size:11px;color:#999;margin:0 0 12px;text-align:center;font-family:sans-serif">{must_read_titles}</p>
      <div style="text-align:center">{stars}</div>
    </div>

    <div style="padding:18px 40px;text-align:center">
      <p style="color:#bbb;font-size:11px;margin:0;font-family:sans-serif">Generated by Claude &bull; Delivered every Saturday &bull; farrer36.com</p>
    </div>
  </div>
</body></html>"""
