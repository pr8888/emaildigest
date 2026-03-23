import anthropic
import json
import os
import re
from collections import Counter

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _extract_sender_name(sender: str) -> str:
    """Turn 'Citrini Research <email@example.com>' into 'Citrini Research'."""
    match = re.match(r'^"?([^"<]+)"?\s*<', sender or "")
    if match:
        return match.group(1).strip()
    local = (sender or "").split("@")[0]
    return local.replace(".", " ").replace("_", " ").title() or "Unknown"


def summarize_article(text: str, subject: str) -> tuple:
    """Returns (summary, tags, must_read_score)."""
    text = text[:8000]  # Stay well within token limits

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": f"""Summarize this investing article for a finance professional. The user personally selected and forwarded this email, so treat it as worth summarising regardless of topic — equities (any sector including gaming, commodities, healthcare, real estate etc.), macro, fixed income, private markets, all count.

Subject: {subject}

Content:
{text}

Respond with JSON only:
{{
  "summary": "2-3 sentences capturing the key insight and actionable takeaway from whatever content is available",
  "tags": ["macro" and/or "equities" and/or "other"],
  "must_read_score": 0.0 to 1.0,
  "is_paywalled": true or false
}}

Scoring — rate the relevance and insight of the content that IS present, regardless of length:
- 0.7–1.0: genuinely fascinating or actionable — novel framework, high-conviction call, data that changes how you think about a market
- 0.4–0.6: useful and on-topic but not exceptional — solid context, decent analysis, nothing you haven't broadly heard before
- 0.0–0.3: a sales pitch, pure promotional content, or so generic it adds no value

is_paywalled — set true if the content appears truncated: hits a paywall mid-article, ends with "subscribe to read more", or is clearly just a teaser with minimal substance. Set false if the full article is present."""
        }]
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if Claude wrapped the JSON
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    result = json.loads(raw.strip())
    return result["summary"], result["tags"], result["must_read_score"], result.get("is_paywalled", False)


def compose_digest(articles, feedback_history, digest_id: int, app_url: str) -> tuple:
    """Returns (html, plain_text) for the weekly digest email."""
    # Full articles first (sorted by score), paywalled articles after (sorted by score)
    sorted_articles = sorted(
        articles,
        key=lambda a: (bool(a.is_paywalled), -a.must_read_score)
    )
    total_count = len(sorted_articles)

    # Filter out junk (score below 0.3) — everything else gets included
    top_articles = [a for a in sorted_articles if a.must_read_score >= 0.3]

    # Build feedback context for Claude
    feedback_note = ""
    if feedback_history:
        length_votes = [f.value for f in feedback_history if f.type == "length"]
        if length_votes:
            top = Counter(length_votes).most_common(1)[0][0]
            length_map = {"short": "longer", "good": "the same length", "long": "shorter"}
            feedback_note = f"Based on past feedback, write the digest {length_map.get(top, 'the same length')} than usual."

    # Format articles for Claude — include author/source
    articles_text = ""
    for i, a in enumerate(top_articles):
        source = _extract_sender_name(a.sender)
        articles_text += f"\n[{i+1}] Source: {source}\nSubject: {a.subject}\nSummary: {a.summary}\nScore: {a.must_read_score:.2f}\nTags: {', '.join(a.tags or [])}\n"

    volume_note = f"There are {len(top_articles)} articles this week (filtered from {total_count} total, excluding low-quality)."

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": f"""Write a weekly investing digest for Pratyush Rastogi, a bottom-up fundamental equity investor based in Singapore. {feedback_note}

Pratyush's priorities: he is primarily a stock-picker — company-specific analysis, earnings, sector dynamics and individual equity ideas are his main interest. Macro (rates, FX, geopolitics) is useful context but should always play a supporting role, never the headline. Lead with equities, end with macro.

{volume_note}

Articles this week (sorted by relevance):
{articles_text}

Adapt the format to however many articles are available:
- If 1 article: write a thorough single-article commentary, 8-10 sentences, explaining the key insight and why it matters
- If 2-3 articles: write a "Must Read" section covering all of them with 4-5 sentences each, skip the "Also Worth Reading" section
- If 4+ articles: write all four sections in this order:
    1. "Week in Brief" — 2 sentences capturing the overall theme
    2. "Must Read This Week" — top 2 articles, 4-5 sentences each
    3. "Equities" — stock-specific and sector pieces, 2 sentences each
    4. "Macro" — macro/rates/geopolitical pieces, 2 sentences each (keep this section brief)

Important: whenever you mention an article, include the source/author name in parentheses — e.g. "The Scoreboard and the Supercycle (Citrini Research)". Use the Source field for each article.

Always write something useful — never refuse or ask for more articles.

Tone: smart analyst friend, not a robot. No bullet points — prose only. Total reading time should be 10-12 minutes."""
        }]
    )

    digest_body = response.content[0].text
    base = f"{app_url}/feedback?digest_id={digest_id}"

    html = _build_html(digest_body, base)
    plain = digest_body + f"\n\n---\nFeedback — Length: {base}&type=length&value=short (Too Short) | {base}&type=length&value=good (Just Right) | {base}&type=length&value=long (Too Long)"

    return html, plain


def _build_html(body: str, feedback_base: str) -> str:
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

      <p style="font-size:13px;color:#333;margin:0 0 12px;text-align:center;font-family:sans-serif"><strong>Rate this week's must reads:</strong></p>
      <div style="text-align:center">{stars}</div>
    </div>

    <div style="padding:18px 40px;text-align:center">
      <p style="color:#bbb;font-size:11px;margin:0;font-family:sans-serif">Generated by Claude &bull; Delivered every Saturday &bull; farrer36.com</p>
    </div>
  </div>
</body></html>"""
