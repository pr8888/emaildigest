from datetime import date

# Colour palette matches the existing digest email style
STRONG_COLOR = "#1a7f37"
RECOVERY_COLOR = "#0550ae"
BREAKOUT_COLOR = "#9a3412"
HEADER_BG = "#1a1a2e"


def build_screener_email(clusters, stocks, run_date=None):
    """Returns (html, plain) tuple for the weekly screener email."""
    if run_date is None:
        run_date = date.today().strftime("%b %d, %Y")

    strong = [s for s in stocks if s["signal"] == "Strong"]
    recovery = [s for s in stocks if s["signal"] == "Recovery"]
    breakout = [s for s in stocks if s["signal"] == "Breakout"]

    html = _build_html(clusters, strong, recovery, breakout, run_date)
    plain = _build_plain(clusters, strong, recovery, breakout, run_date)
    return html, plain


# ── HTML ────────────────────────────────────────────────────────────────────

def _signal_badge(signal):
    colors = {
        "Strong": (STRONG_COLOR, "#fff"),
        "Recovery": (RECOVERY_COLOR, "#fff"),
        "Breakout": (BREAKOUT_COLOR, "#fff"),
    }
    bg, fg = colors.get(signal, ("#888", "#fff"))
    return f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600">{signal}</span>'


def _delta_str(delta):
    if delta > 0:
        return f'<span style="color:{STRONG_COLOR}">↑{delta}</span>'
    elif delta < 0:
        return f'<span style="color:#9a3412">↓{abs(delta)}</span>'
    return '<span style="color:#aaa">—</span>'


def _cluster_rows(clusters):
    if not clusters:
        return "<tr><td colspan='6' style='color:#888;padding:12px'>No clusters this week.</td></tr>"
    rows = []
    for c in clusters[:30]:  # cap at top 30 clusters
        delta = c.get("delta", 0)
        rows.append(f"""
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:8px 12px;font-weight:600">{c['sector']}</td>
          <td style="padding:8px 12px;color:#555">{c['country']}</td>
          <td style="padding:8px 12px;text-align:center;color:{STRONG_COLOR};font-weight:700">{c['strong']}</td>
          <td style="padding:8px 12px;text-align:center;color:{RECOVERY_COLOR}">{c['recovery']}</td>
          <td style="padding:8px 12px;text-align:center;color:{BREAKOUT_COLOR}">{c['breakout']}</td>
          <td style="padding:8px 12px;text-align:center;font-weight:600">{c['total']}</td>
          <td style="padding:8px 12px;text-align:center">{_delta_str(delta)}</td>
        </tr>""")
    return "".join(rows)


def _stock_rows(stocks):
    if not stocks:
        return "<tr><td colspan='8' style='color:#888;padding:12px'>None this week.</td></tr>"
    rows = []
    for s in stocks:
        vol_cell = f"{s['vol_ratio']:.0%} {s['vol_flag']}"
        rows.append(f"""
        <tr style="border-bottom:1px solid #f0f0f0">
          <td style="padding:7px 10px;font-weight:600;color:#1a1a2e">{s['symbol']}</td>
          <td style="padding:7px 10px;color:#444;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{s['name']}</td>
          <td style="padding:7px 10px;color:#666">{s['country']}</td>
          <td style="padding:7px 10px;color:#666;font-size:12px">{s['industry']}</td>
          <td style="padding:7px 10px;text-align:right">${s['price']:.2f}</td>
          <td style="padding:7px 10px;text-align:center;color:{RECOVERY_COLOR};font-weight:600">+{s['pct_above_52w']}%</td>
          <td style="padding:7px 10px;text-align:center;color:{BREAKOUT_COLOR};font-weight:600">+{s['pct_above_3m']}%</td>
          <td style="padding:7px 10px;text-align:center;color:#888;font-size:12px">{vol_cell}</td>
        </tr>""")
    return "".join(rows)


def _section_header(title, color, count):
    return f"""
    <h3 style="margin:32px 0 12px;font-size:16px;color:{color};font-family:Georgia,serif">
      {title} <span style="font-size:13px;font-weight:normal;color:#888">({count} stocks)</span>
    </h3>"""


def _stock_table(stocks):
    return f"""
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="background:#f8f9fa;border-bottom:2px solid #dee2e6">
          <th style="padding:8px 10px;text-align:left;color:#555">Symbol</th>
          <th style="padding:8px 10px;text-align:left;color:#555">Name</th>
          <th style="padding:8px 10px;text-align:left;color:#555">Country</th>
          <th style="padding:8px 10px;text-align:left;color:#555">Industry</th>
          <th style="padding:8px 10px;text-align:right;color:#555">Price</th>
          <th style="padding:8px 10px;text-align:center;color:{RECOVERY_COLOR}">vs 52w Low</th>
          <th style="padding:8px 10px;text-align:center;color:{BREAKOUT_COLOR}">vs 3m Low</th>
          <th style="padding:8px 10px;text-align:center;color:#888">Vol Ratio</th>
        </tr>
      </thead>
      <tbody>{_stock_rows(stocks)}</tbody>
    </table>"""


def _build_html(clusters, strong, recovery, breakout, run_date):
    total = len(strong) + len(recovery) + len(breakout)
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f3fa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="max-width:900px;margin:32px auto;padding:0 16px">

  <!-- Header -->
  <div style="background:{HEADER_BG};border-radius:12px 12px 0 0;padding:28px 36px">
    <div style="font-size:11px;letter-spacing:2px;color:#8899bb;text-transform:uppercase;margin-bottom:6px">Weekly Stock Screen</div>
    <div style="font-size:24px;font-weight:700;color:#fff;font-family:Georgia,serif">{run_date}</div>
    <div style="font-size:14px;color:#aab;margin-top:6px">{total} qualifying stocks across {len(clusters)} clusters</div>
  </div>

  <!-- Signal guide -->
  <div style="background:#fff;padding:20px 36px;border-bottom:1px solid #eee">
    <div style="font-size:12px;color:#888;margin-bottom:10px;text-transform:uppercase;letter-spacing:1px">How to read this</div>
    <div style="display:flex;gap:24px;flex-wrap:wrap">
      <div>{_signal_badge("Strong")} &nbsp;30%+ above both 52-week low <em>and</em> 3-month low — highest conviction</div>
      <div>{_signal_badge("Recovery")} &nbsp;30%+ above 52-week low — bombed-out stocks climbing back</div>
      <div>{_signal_badge("Breakout")} &nbsp;30%+ above 3-month low — recent range break, momentum building</div>
    </div>
    <div style="margin-top:10px;font-size:12px;color:#aaa">Vol Ratio = last 5 days avg volume ÷ 3-month avg volume. ⚠ = unusually quiet (&lt;50%).</div>
  </div>

  <!-- Cluster table -->
  <div style="background:#fff;padding:28px 36px;margin-top:2px;border-radius:0">
    <div style="font-size:18px;font-weight:700;color:#1a1a2e;font-family:Georgia,serif;margin-bottom:16px">Top Clusters</div>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="background:#f8f9fa;border-bottom:2px solid #dee2e6">
          <th style="padding:8px 12px;text-align:left;color:#555">Sector</th>
          <th style="padding:8px 12px;text-align:left;color:#555">Country</th>
          <th style="padding:8px 12px;text-align:center;color:{STRONG_COLOR}">Strong</th>
          <th style="padding:8px 12px;text-align:center;color:{RECOVERY_COLOR}">Recovery</th>
          <th style="padding:8px 12px;text-align:center;color:{BREAKOUT_COLOR}">Breakout</th>
          <th style="padding:8px 12px;text-align:center;color:#333">Total</th>
          <th style="padding:8px 12px;text-align:center;color:#888">vs Last Week</th>
        </tr>
      </thead>
      <tbody>{_cluster_rows(clusters)}</tbody>
    </table>
  </div>

  <!-- Strong stocks -->
  <div style="background:#fff;padding:28px 36px;margin-top:2px">
    {_section_header("Strong Signals", STRONG_COLOR, len(strong))}
    <p style="font-size:13px;color:#888;margin:0 0 12px">30%+ above both 52-week low and 3-month low. Both momentum and value signals firing.</p>
    {_stock_table(strong)}
  </div>

  <!-- Recovery stocks -->
  <div style="background:#fff;padding:28px 36px;margin-top:2px">
    {_section_header("Recovery Signals", RECOVERY_COLOR, len(recovery))}
    <p style="font-size:13px;color:#888;margin:0 0 12px">30%+ above 52-week low only. Deep-value stocks that are climbing back.</p>
    {_stock_table(recovery)}
  </div>

  <!-- Breakout stocks -->
  <div style="background:#fff;padding:28px 36px;margin-top:2px;border-radius:0 0 12px 12px">
    {_section_header("Breakout Signals", BREAKOUT_COLOR, len(breakout))}
    <p style="font-size:13px;color:#888;margin:0 0 12px">30%+ above 3-month low only. Recent momentum — watch these for continuation.</p>
    {_stock_table(breakout)}
  </div>

  <div style="text-align:center;padding:24px;color:#bbb;font-size:12px">
    farrer36.com &bull; Weekly Stock Screen &bull; End-of-day data via Financial Modeling Prep
  </div>

</div>
</body>
</html>"""


# ── PLAIN TEXT ───────────────────────────────────────────────────────────────

def _build_plain(clusters, strong, recovery, breakout, run_date):
    lines = [
        f"WEEKLY STOCK SCREEN — {run_date}",
        "=" * 60,
        f"Total: {len(strong) + len(recovery) + len(breakout)} stocks, {len(clusters)} clusters",
        "",
        "SIGNALS",
        "  Strong   = 30%+ above 52w low AND 3m low (highest conviction)",
        "  Recovery = 30%+ above 52w low (deep value recovering)",
        "  Breakout = 30%+ above 3m low  (recent momentum)",
        "",
        "TOP CLUSTERS",
        "-" * 60,
        f"{'Sector':<25} {'Country':<12} {'Strong':>6} {'Recov':>6} {'Break':>6} {'Total':>6} {'Delta':>6}",
        "-" * 60,
    ]
    for c in clusters[:30]:
        delta = c.get("delta", 0)
        delta_str = f"+{delta}" if delta > 0 else str(delta) if delta != 0 else "—"
        lines.append(
            f"{c['sector']:<25} {c['country']:<12} {c['strong']:>6} {c['recovery']:>6} {c['breakout']:>6} {c['total']:>6} {delta_str:>6}"
        )

    for label, group in [("STRONG SIGNALS", strong), ("RECOVERY SIGNALS", recovery), ("BREAKOUT SIGNALS", breakout)]:
        lines += ["", label, "-" * 60,
                  f"{'Symbol':<10} {'Name':<30} {'Ctry':<6} {'vs52w':>7} {'vs3m':>7} {'Vol%':>6}",
                  "-" * 60]
        for s in group:
            lines.append(
                f"{s['symbol']:<10} {s['name'][:29]:<30} {s['country']:<6} "
                f"+{s['pct_above_52w']:>5}% +{s['pct_above_3m']:>5}% {s['vol_ratio']:>5.0%}{s['vol_flag']}"
            )
        if not group:
            lines.append("  None this week.")

    lines += ["", "-" * 60, "farrer36.com | Weekly Stock Screen | Data: Financial Modeling Prep"]
    return "\n".join(lines)
