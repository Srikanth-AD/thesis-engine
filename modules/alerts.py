"""
Alert Delivery + Notification Logging

Sends HTML emails via Gmail SMTP.
Maintains logs/notifications.md and logs/notifications.jsonl for audit trail.
"""
import json
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "")
EMAIL_PASS   = os.environ.get("EMAIL_PASSWORD", "")


# ----------------------------------------------------------------------
# Email formatting (HTML)
# ----------------------------------------------------------------------

def _action_badge(claude_response, ticker):
    """
    Extract the recommended action for a ticker from the LLM response.

    Returns:
        Tuple of (label, text_color, background_color).
    """
    for line in claude_response.split("\n"):
        line_upper = line.upper()
        if ticker.upper() in line_upper and "ACTION" in line_upper:
            if "BUY MORE" in line_upper or "ADD" in line_upper:
                return "BUY MORE", "#22c55e", "#f0fdf4"
            elif "SELL" in line_upper or "EXIT" in line_upper or "REDUCE" in line_upper:
                return "SELL", "#ef4444", "#fef2f2"
            else:
                return "KEEP", "#6b7280", "#f9fafb"
    return "KEEP", "#6b7280", "#f9fafb"


def _stock_note(claude_response, ticker):
    """
    Extract the LLM's note for a specific ticker from the response text.

    Returns:
        A short string summarizing the LLM's view, or empty string.
    """
    lines = claude_response.split("\n")
    for i, line in enumerate(lines):
        if ticker.upper() in line.upper() and (
            "THESIS" in line.upper() or "STATUS" in line.upper()
        ):
            notes = []
            for j in range(i, min(i + 4, len(lines))):
                l = lines[j].strip().strip("*").strip("-").strip()
                if l and not l.startswith("CONTEXT_UPDATE"):
                    l = l.replace("**", "").replace("##", "").strip()
                    if ticker.upper() in l.upper() and "\u2014" in l:
                        l = l.split("\u2014", 1)[1].strip()
                    elif ticker.upper() in l.upper() and ":" in l:
                        parts = l.split(":", 1)
                        if len(parts) > 1:
                            l = parts[1].strip()
                    notes.append(l)
            return " ".join(notes[:2])
    return ""


def _extract_section(claude_response, header):
    """
    Extract a section from the LLM response by header keyword.

    Args:
        claude_response: Full text of the LLM response.
        header:          Section header keyword to search for.

    Returns:
        List of content strings from that section.
    """
    lines = claude_response.split("\n")
    result = []
    capturing = False
    for line in lines:
        line_upper = line.upper().strip()
        if header.upper() in line_upper:
            capturing = True
            after = line.split(":", 1)[1].strip() if ":" in line else ""
            if after:
                result.append(after)
            continue
        if capturing:
            if line.strip() == "" and result:
                break
            # Stop at next major section
            if any(
                h in line_upper
                for h in [
                    "CONTEXT_UPDATE", "##", "BIGGEST", "URGENT",
                    "WATCHLIST", "NEW DISCOVER",
                ]
            ) and result:
                break
            if line.strip():
                result.append(line.strip().lstrip("- ").lstrip("* "))
    return result


def _format_html_email(subject, claude_response, portfolio, data, alert_type):
    """
    Create a clean, readable HTML email summarizing the analysis.

    Args:
        subject:         Email subject line.
        claude_response: Full text of the LLM analysis.
        portfolio:       Parsed portfolio config.
        data:            Dict of all layer results.
        alert_type:      'URGENT ALERT' or 'DIGEST'.

    Returns:
        HTML string for the email body.
    """
    prices = data.get("prices", {})
    total_pnl_pct = prices.get("__portfolio_pnl_pct__", 0)
    total_pnl     = prices.get("__total_pnl__", 0)
    total_current = prices.get("__total_current__", 0)
    pnl_color     = "#22c55e" if total_pnl >= 0 else "#ef4444"
    now_str       = datetime.now().strftime("%A, %B %d at %I:%M %p")
    is_urgent     = alert_type.upper() == "URGENT ALERT"

    # Build stock rows
    stock_rows = ""
    for stock in portfolio.get("portfolio", []):
        ticker = stock["ticker"]
        name   = stock.get("name", ticker)
        p = prices.get(ticker, {})
        if not p or p.get("error"):
            continue

        price     = p.get("price", 0)
        change    = p.get("change_pct", 0)
        pnl       = p.get("pnl", 0)
        pnl_pct   = p.get("pnl_pct", 0)
        day_color = "#22c55e" if change >= 0 else "#ef4444"
        pos_color = "#22c55e" if pnl >= 0 else "#ef4444"
        action_label, action_color, action_bg = _action_badge(claude_response, ticker)
        note = _stock_note(claude_response, ticker)

        stock_rows += f"""
        <tr>
          <td style="padding:12px 16px;border-bottom:1px solid #f0f0f0;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <div>
                <span style="font-weight:700;font-size:16px;color:#1a1a1a;">{ticker}</span>
                <span style="color:#888;font-size:13px;margin-left:6px;">{name}</span>
              </div>
            </div>
            <table cellpadding="0" cellspacing="0" style="margin-top:6px;width:100%;">
              <tr>
                <td style="font-size:14px;color:#333;">${price:,.2f}
                  <span style="color:{day_color};font-size:13px;margin-left:4px;">{change:+.1f}% today</span>
                </td>
                <td style="text-align:center;font-size:13px;color:{pos_color};">P&L: {pnl_pct:+.1f}% (${pnl:+,.0f})</td>
                <td style="text-align:right;">
                  <span style="background:{action_bg};color:{action_color};font-weight:700;font-size:12px;padding:3px 10px;border-radius:12px;border:1px solid {action_color};">{action_label}</span>
                </td>
              </tr>
            </table>
            {"<div style='margin-top:6px;font-size:13px;color:#555;line-height:1.4;'>" + note + "</div>" if note else ""}
          </td>
        </tr>"""

    # Build watchlist rows
    watchlist_html = ""
    watchlist = portfolio.get("watchlist", [])[:5]
    if watchlist:
        wl_rows = ""
        for w in watchlist:
            wt      = w["ticker"]
            wname   = w.get("name", wt)
            wreason = w.get("reason", "")[:100]
            wentry  = w.get("entry_notes", "")
            wl_rows += f"""
            <tr>
              <td style="padding:10px 16px;border-bottom:1px solid #f0f0f0;">
                <span style="font-weight:700;color:#1a1a1a;">{wt}</span>
                <span style="color:#888;font-size:13px;margin-left:6px;">{wname}</span>
                <div style="font-size:13px;color:#555;margin-top:4px;">{wreason}</div>
                {"<div style='font-size:12px;color:#3b82f6;margin-top:2px;'>Entry: " + wentry + "</div>" if wentry else ""}
              </td>
            </tr>"""

        watchlist_html = f"""
        <table cellpadding="0" cellspacing="0" width="100%" style="margin-top:24px;">
          <tr><td style="padding:0 16px 8px;"><h2 style="margin:0;font-size:16px;color:#1a1a1a;">Watching</h2></td></tr>
          {wl_rows}
        </table>"""

    # Extract key sections from LLM response
    risk_items      = _extract_section(claude_response, "BIGGEST RISK")
    opp_items       = _extract_section(claude_response, "BIGGEST OPPORTUNITY")
    discovery_items = _extract_section(claude_response, "NEW DISCOVER")

    insights_html = ""
    if risk_items or opp_items or discovery_items:
        insights_html = (
            '<table cellpadding="0" cellspacing="0" width="100%" style="margin-top:24px;">'
            '<tr><td style="padding:0 16px 8px;">'
            '<h2 style="margin:0;font-size:16px;color:#1a1a1a;">Key Takeaways</h2>'
            '</td></tr>'
        )

        if risk_items:
            insights_html += (
                '<tr><td style="padding:8px 16px;">'
                '<div style="background:#fef2f2;border-left:3px solid #ef4444;'
                'padding:10px 14px;border-radius:6px;font-size:13px;color:#991b1b;'
                f'line-height:1.5;">{"<br>".join(risk_items)}</div></td></tr>'
            )

        if opp_items:
            insights_html += (
                '<tr><td style="padding:8px 16px;">'
                '<div style="background:#f0fdf4;border-left:3px solid #22c55e;'
                'padding:10px 14px;border-radius:6px;font-size:13px;color:#166534;'
                f'line-height:1.5;">{"<br>".join(opp_items)}</div></td></tr>'
            )

        if discovery_items:
            disc_text = "<br>".join(discovery_items)
            insights_html += (
                '<tr><td style="padding:8px 16px;">'
                '<div style="background:#eff6ff;border-left:3px solid #3b82f6;'
                'padding:10px 14px;border-radius:6px;font-size:13px;color:#1e40af;'
                f'line-height:1.5;"><strong>Worth a look:</strong><br>{disc_text}'
                '</div></td></tr>'
            )

        insights_html += "</table>"

    # Header bar color
    header_bg    = "#dc2626" if is_urgent else "#1a1a1a"
    header_label = "URGENT ALERT" if is_urgent else "Daily Digest"

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table cellpadding="0" cellspacing="0" width="100%" style="max-width:600px;margin:0 auto;background:#ffffff;">

  <!-- Header -->
  <tr>
    <td style="background:{header_bg};padding:20px 16px;text-align:center;">
      <div style="font-size:12px;color:rgba(255,255,255,0.7);text-transform:uppercase;letter-spacing:1px;">{header_label}</div>
      <div style="font-size:18px;color:#fff;font-weight:700;margin-top:4px;">{now_str}</div>
    </td>
  </tr>

  <!-- Portfolio total -->
  <tr>
    <td style="padding:20px 16px;text-align:center;border-bottom:1px solid #eee;">
      <div style="font-size:28px;font-weight:700;color:#1a1a1a;">${total_current:,.0f}</div>
      <div style="font-size:16px;color:{pnl_color};font-weight:600;margin-top:2px;">{total_pnl_pct:+.1f}% (${total_pnl:+,.0f})</div>
    </td>
  </tr>

  <!-- Stocks -->
  {stock_rows}

  <!-- Watchlist -->
  {watchlist_html}

  <!-- Insights -->
  {insights_html}

</table>
</body>
</html>"""

    return html


def _send_email(subject, html_body):
    """
    Send an HTML email via Gmail SMTP.

    Requires NOTIFY_EMAIL and EMAIL_PASSWORD environment variables.

    Returns:
        True on success, False on failure.
    """
    if not NOTIFY_EMAIL or not EMAIL_PASS:
        print("  Warning: Email not configured -- set NOTIFY_EMAIL and EMAIL_PASSWORD")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = NOTIFY_EMAIL
        msg["To"]      = NOTIFY_EMAIL
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(NOTIFY_EMAIL, EMAIL_PASS)
            server.sendmail(NOTIFY_EMAIL, NOTIFY_EMAIL, msg.as_string())
        return True
    except Exception as e:
        print(f"  Email failed: {e}")
        return False


# ----------------------------------------------------------------------
# Notification logging
# ----------------------------------------------------------------------

def log_notification(alert_type, subject, claude_response, data,
                     layers_triggered=None, recommendation=None):
    """
    Log a notification to both markdown and JSONL files.

    Appends to:
    - logs/notifications.md   (human-readable)
    - logs/notifications.jsonl (machine-readable)

    Args:
        alert_type:       'URGENT ALERT' or 'DIGEST'.
        subject:          Email subject line.
        claude_response:  Full LLM response text.
        data:             Dict of all layer results.
        layers_triggered: Optional list of layer names that triggered the alert.
        recommendation:   Optional recommendation string.
    """
    os.makedirs("logs", exist_ok=True)

    now = datetime.now()
    prices = data.get("prices", {}) if data else {}

    # -- Human-readable markdown -----------------------------------------------
    md_lines = [
        "\n---\n",
        f"## {now.strftime('%Y-%m-%d %H:%M ET')} -- {alert_type.upper()} SENT\n",
        f"**Subject:** {subject}\n",
    ]

    if layers_triggered:
        md_lines.append(f"**Layers triggered:** {', '.join(layers_triggered)}\n")

    if recommendation:
        md_lines.append(f"**Recommendation:** {recommendation}\n")

    # Portfolio context at time of alert
    md_lines.append("\n**Portfolio at time of alert:**\n")
    for ticker, p in prices.items():
        if ticker.startswith("__") or not isinstance(p, dict) or p.get("error"):
            continue
        md_lines.append(
            f"- {ticker}: ${p.get('price', 0):.2f} "
            f"({p.get('change_pct', 0):+.1f}%) | "
            f"P&L: {p.get('pnl_pct', 0):+.1f}%\n"
        )

    md_lines.append("\n**Analysis:**\n")
    md_lines.append(
        claude_response[:800] + ("..." if len(claude_response) > 800 else "")
    )
    md_lines.append("\n")

    with open("logs/notifications.md", "a") as f:
        f.writelines(md_lines)

    # -- Machine-readable JSON -------------------------------------------------
    entry = {
        "timestamp":          now.isoformat(),
        "type":               alert_type,
        "subject":            subject,
        "layers_triggered":   layers_triggered or [],
        "recommendation":     recommendation,
        "portfolio_snapshot": {
            k: {
                "price":      v.get("price"),
                "pnl_pct":    v.get("pnl_pct"),
                "change_pct": v.get("change_pct"),
            }
            for k, v in prices.items()
            if not k.startswith("__") and isinstance(v, dict) and not v.get("error")
        },
        "response_preview": claude_response[:400],
    }

    with open("logs/notifications.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")

    print("  Logged to notifications.md and notifications.jsonl")


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def send_urgent_alert(subject, claude_response, portfolio, data,
                      layers_triggered=None):
    """
    Send an urgent intraday alert email.

    Args:
        subject:          Email subject line.
        claude_response:  Full LLM analysis text.
        portfolio:        Parsed portfolio config.
        data:             Dict of all layer results.
        layers_triggered: Optional list of layer names that triggered the alert.

    Returns:
        True if email was sent successfully.
    """
    body    = _format_html_email(subject, claude_response, portfolio, data, "URGENT ALERT")
    success = _send_email(subject, body)
    if success:
        print("  Urgent alert delivered")
    return success


def send_digest(subject, claude_response, portfolio, data):
    """
    Send the daily or weekend digest email.

    Args:
        subject:         Email subject line.
        claude_response: Full LLM analysis text.
        portfolio:       Parsed portfolio config.
        data:            Dict of all layer results.

    Returns:
        True if email was sent successfully.
    """
    body    = _format_html_email(subject, claude_response, portfolio, data, "DIGEST")
    success = _send_email(subject, body)
    if success:
        print("  Digest delivered")
    return success
