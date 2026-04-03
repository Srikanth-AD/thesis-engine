#!/usr/bin/env python3
"""
thesis-engine -- Main Orchestrator

Runs 14 data layers in parallel, assembles a structured prompt for Claude,
and sends email alerts when material developments affect your investment thesis.

Usage:
    python analyzer.py --once           Run once and exit
    python analyzer.py --once --test    Run without sending alerts (print only)
    python analyzer.py --loop           Run every hour (local scheduler)
"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from datetime import date, datetime

import schedule
import yaml
from dotenv import load_dotenv

load_dotenv()

import anthropic

from modules.alerts import log_notification, send_digest, send_urgent_alert
from modules.congress_trades import fetch_congress_trades
from modules.fundamentals import fetch_fundamentals
from modules.google_trends import fetch_google_trends
from modules.hedge_funds import fetch_hedge_funds
from modules.insider_trades import fetch_insider_trades
from modules.macro import fetch_macro
from modules.news_rss import fetch_news_rss
from modules.press_releases import fetch_press_releases
from modules.prices import fetch_prices
from modules.reddit import fetch_reddit_sentiment
from modules.sustainability import extract_sustainability_signals
from modules.technicals import calculate_technicals
from modules.wikipedia import fetch_wikipedia_views
from modules.world_news import fetch_world_news

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_portfolio():
    """Load portfolio configuration from stocks.yaml."""
    with open("stocks.yaml", "r") as f:
        return yaml.safe_load(f)


def is_weekend():
    """Check if today is Saturday or Sunday."""
    return datetime.now().weekday() >= 5


def is_eod():
    """End of trading day -- time to send daily digest (3:45pm+ ET)."""
    now = datetime.now()
    return now.hour == 15 and now.minute >= 45


def is_sunday_prep():
    """Sunday evening prep run (5pm+ ET)."""
    now = datetime.now()
    return now.weekday() == 6 and now.hour >= 17


# ---------------------------------------------------------------------------
# Data fetching -- 13 layers run in parallel via ThreadPoolExecutor
# ---------------------------------------------------------------------------

def fetch_all_data(portfolio, weekend=False):
    """
    Run all data modules. Weekend mode skips price/technical/macro
    since markets are closed.

    Returns dict keyed by layer name.
    """
    tickers = [s["ticker"] for s in portfolio["portfolio"]]
    watchlist = [s["ticker"] for s in portfolio.get("watchlist", [])]
    all_tickers = tickers + watchlist

    results = {}

    print("  Fetching data layers in parallel...")

    # Layers that run every cycle (weekday + weekend)
    always_run = {
        "news_rss": lambda: fetch_news_rss(all_tickers),
        "press_releases": lambda: fetch_press_releases(tickers, portfolio),
        "world_news": lambda: fetch_world_news(portfolio),
        "reddit": lambda: fetch_reddit_sentiment(all_tickers),
        "google_trends": lambda: fetch_google_trends(all_tickers),
        "wikipedia": lambda: fetch_wikipedia_views(tickers, portfolio),
        "congress_trades": lambda: fetch_congress_trades(tickers, portfolio),
    }

    # Layers that only run on weekdays (markets open)
    weekday_only = {
        "prices": lambda: fetch_prices(tickers, portfolio),
        "fundamentals": lambda: fetch_fundamentals(tickers),
        "technicals": lambda: calculate_technicals(tickers),
        "macro": lambda: fetch_macro(),
        "hedge_funds": lambda: fetch_hedge_funds(tickers),
        "insider_trades": lambda: fetch_insider_trades(tickers),
    }

    layers_to_run = dict(always_run)
    if not weekend:
        layers_to_run.update(weekday_only)

    # Run all layers in parallel (6 workers, 90s global timeout)
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fn): name for name, fn in layers_to_run.items()}
        try:
            for future in as_completed(futures, timeout=90):
                name = futures[future]
                try:
                    results[name] = future.result()
                    print(f"    [ok] {name}")
                except Exception as e:
                    results[name] = {"error": str(e)}
                    print(f"    [!!] {name}: {e}")
        except TimeoutError:
            for future, name in futures.items():
                if name not in results:
                    future.cancel()
                    results[name] = {"error": "timed out"}
                    print(f"    [!!] {name}: timed out")

    return results


# ---------------------------------------------------------------------------
# Prompt assembly -- all 14 layers into one structured Claude prompt
# ---------------------------------------------------------------------------

def build_prompt(portfolio, data, weekend=False):
    """
    Assemble all layer data into a single structured prompt for Claude.
    The prompt includes thesis context, watchlist, and an analysis request
    that asks Claude to evaluate each stock's thesis status.
    """
    run_type = "WEEKEND PREP" if weekend else "MARKET HOURS"
    now_str = datetime.now().strftime("%A %B %d %Y %H:%M ET")

    lines = [
        f"PORTFOLIO ANALYSIS -- {run_type} | {now_str}",
        f"Goal: {portfolio['meta']['investor_goal']} | Risk: {portfolio['meta']['risk_profile']}",
        "",
    ]

    # -- Layers 1-3: Price, Fundamentals, Technicals --
    if not weekend:
        lines.append("=== LAYERS 1-3: PRICE / FUNDAMENTALS / TECHNICALS ===")
        prices = data.get("prices", {})
        funds = data.get("fundamentals", {})
        techs = data.get("technicals", {})

        for stock in portfolio["portfolio"]:
            t = stock["ticker"]
            p = prices.get(t, {})
            f = funds.get(t, {})
            tc = techs.get(t, {})

            if p.get("error"):
                lines.append(f"\n{t}: price unavailable -- {p['error']}")
                continue

            # Earnings countdown
            earn_str = ""
            if stock.get("earnings_date"):
                try:
                    ed = date.fromisoformat(stock["earnings_date"])
                    days = (ed - date.today()).days
                    if 0 <= days <= 10:
                        earn_str = f" | EARNINGS IN {days} DAYS"
                    elif days > 0:
                        earn_str = f" | Earnings: {stock['earnings_date']} ({days}d)"
                except Exception:
                    pass

            lines.append(f"""
{t} ({stock['name']}) | {stock['role'].upper()} | Target {stock['target_multiple']}x{earn_str}
  Price:  ${p.get('price','N/A')} ({p.get('change_pct',0):+.1f}% today) | Vol: {p.get('volume_today',0):,} | 52wk: {p.get('52w_position','N/A')}
  P&L:    ${p.get('pnl',0):+.0f} ({p.get('pnl_pct',0):+.1f}%) vs cost ${p.get('blended_cost',0):.2f} | Invested: ${p.get('invested',0):.0f}
  Valuation: PE={f.get('pe','N/A')} FwdPE={f.get('fwd_pe','N/A')} PS={f.get('ps','N/A')} EV/EBITDA={f.get('ev_ebitda','N/A')}
  Health:    D/E={f.get('debt_equity','N/A')} GrossMargin={f.get('gross_margin','N/A')}% OpMargin={f.get('op_margin','N/A')}% FCF={f.get('fcf','N/A')}%
  Market:    ShortInt={f.get('short_interest','N/A')}% | Consensus={f.get('analyst_consensus','N/A')} ({f.get('analyst_count',0)}) | Target=${f.get('price_target','N/A')}
  Technicals: RSI={tc.get('rsi','N/A')} | MACD={tc.get('macd_signal','N/A')} | BB={tc.get('bb_position','N/A')} | Vol {tc.get('volume_vs_avg',1):.1f}x avg | ATR={tc.get('atr','N/A')}""")

        total_pnl_pct = prices.get("__portfolio_pnl_pct__", 0)
        total_pnl = prices.get("__total_pnl__", 0)
        total_current = prices.get("__total_current__", 0)
        lines.append(f"\nPORTFOLIO TOTAL: ${total_current:,.0f} | Net P&L: ${total_pnl:+,.0f} ({total_pnl_pct:+.1f}%)\n")

    # -- Layer 4: Macro --
    if not weekend:
        lines.append("=== LAYER 4: MACRO ===")
        m = data.get("macro", {})
        if not m.get("error"):
            lines.append(
                f"Fed Rate: {m.get('fed_rate','N/A')}% | 10yr: {m.get('treasury_10y','N/A')}% | "
                f"2yr: {m.get('treasury_2y','N/A')}% | Curve: {m.get('yield_curve','N/A')}"
            )
            lines.append(
                f"CPI: {m.get('cpi','N/A')}% ({m.get('cpi_trend','N/A')}) | "
                f"PCE: {m.get('pce','N/A')}% | Unemployment: {m.get('unemployment','N/A')}%"
            )
            lines.append(
                f"VIX: {m.get('vix','N/A')} | Oil WTI: ${m.get('oil_wti','N/A')} | "
                f"DXY: {m.get('dxy','N/A')}"
            )
        lines.append("")

    # -- Layer 5: News RSS --
    lines.append("=== LAYER 5: NEWS RSS ===")
    news = data.get("news_rss", {})
    for stock in portfolio["portfolio"]:
        t = stock["ticker"]
        t_news = news.get(t, [])
        if t_news:
            for item in t_news[:3]:
                sent = item.get("sentiment", "neutral")
                icon = "[+]" if sent == "positive" else ("[-]" if sent == "negative" else "[.]")
                lines.append(f"{icon} {t} [{item.get('age','?')}] ({item.get('source','?')}): {item.get('title','')}")
    lines.append("")

    # -- Layer 6: Press Releases / 8-K --
    lines.append("=== LAYER 6: PRESS RELEASES & 8-K FILINGS ===")
    prs = data.get("press_releases", {})
    any_pr = False
    for stock in portfolio["portfolio"]:
        t = stock["ticker"]
        t_prs = prs.get(t, [])
        for pr in t_prs[:2]:
            any_pr = True
            pr_type = pr.get("type", "general")
            label = {"dilution": "DILUTION", "contract": "CONTRACT", "executive": "EXEC"}.get(pr_type, "INFO")
            lines.append(f"[{label}] {t} [{pr.get('date','?')}] ({pr.get('source','?')}): {pr.get('title','')}")
            if pr.get("summary"):
                lines.append(f"    -> {pr['summary'][:120]}")
    if not any_pr:
        lines.append("No significant press releases in last 7 days.")
    lines.append("")

    # -- Layer 7: GDELT World News --
    lines.append("=== LAYER 7: WORLD NEWS & GEOPOLITICS (GDELT) ===")
    world = data.get("world_news", {})
    if not world.get("error"):
        lines.append(f"Global tone: {world.get('tone_score','N/A')}/10 ({world.get('tone_label','N/A')})")
        for event in world.get("top_events", [])[:5]:
            lines.append(f"  - {event}")
        for theme, td in world.get("theme_summaries", {}).items():
            lines.append(f"  [{theme}] avg tone: {td.get('avg_tone','N/A')}")
    lines.append("")

    # -- Layer 8: Reddit --
    lines.append("=== LAYER 8: REDDIT SENTIMENT ===")
    reddit = data.get("reddit", {})
    for stock in portfolio["portfolio"]:
        t = stock["ticker"]
        r = reddit.get(t, {})
        if r and not r.get("error"):
            spike = " **SPIKE**" if r.get("spike") else ""
            lines.append(
                f"{t}: {r.get('mentions_24h',0)} mentions/24h "
                f"({r.get('velocity_pct',0):+.0f}% vs avg){spike} | "
                f"{r.get('bullish_pct',50):.0f}% bullish"
            )
            if r.get("top_post"):
                p = r["top_post"]
                q = "(Quality DD)" if p.get("quality") else ""
                lines.append(f'  Top: "{p["title"]}" ({p.get("score",0)} pts, r/{p.get("subreddit","?")}) {q}')
    lines.append("")

    # -- Layer 9: Google Trends --
    lines.append("=== LAYER 9: GOOGLE TRENDS ===")
    trends = data.get("google_trends", {})
    for stock in portfolio["portfolio"]:
        t = stock["ticker"]
        tr = trends.get(t, {})
        if tr and not tr.get("error"):
            spike = " **SPIKE**" if tr.get("spike") else ""
            lines.append(
                f"{t}: score {tr.get('score','N/A')}/100 "
                f"({tr.get('change_pct',0):+.0f}% vs 30d avg){spike}"
            )
    lines.append("")

    # -- Layer 10: Wikipedia --
    lines.append("=== LAYER 10: WIKIPEDIA PAGE VIEWS ===")
    wiki = data.get("wikipedia", {})
    for stock in portfolio["portfolio"]:
        t = stock["ticker"]
        w = wiki.get(t, {})
        if w and not w.get("error"):
            spike = " **SPIKE**" if w.get("spike") else ""
            lines.append(
                f"{t}: {w.get('views_today','N/A'):,} views/day "
                f"({w.get('spike_multiple',1):.1f}x avg){spike}"
            )
    lines.append("")

    # -- Layer 11: Hedge Funds --
    if not weekend:
        lines.append("=== LAYER 11: HEDGE FUND 13F (45-day lag) ===")
        hf = data.get("hedge_funds", {})
        for stock in portfolio["portfolio"]:
            t = stock["ticker"]
            h = hf.get(t, {})
            if h and not h.get("error"):
                lines.append(
                    f"{t}: {h.get('fund_count','N/A')} recent 13F filings | "
                    f"Notable: {h.get('notable','N/A')}"
                )
        lines.append("")

    # -- Layer 12: Insider Trades --
    if not weekend:
        lines.append("=== LAYER 12: INSIDER TRADES (Form 4, last 90 days) ===")
        insider = data.get("insider_trades", {})
        for stock in portfolio["portfolio"]:
            t = stock["ticker"]
            i = insider.get(t, {})
            if i and not i.get("error") and i.get("trades"):
                net = i.get("net_sentiment", "neutral")
                label = {"bullish": "[BUY]", "bearish": "[SELL]"}.get(net, "[--]")
                lines.append(
                    f"{label} {t}: ${i.get('net_buy_sell',0):+,.0f} net | "
                    f"Bought: ${i.get('total_bought',0):,.0f} | "
                    f"Sold: ${i.get('total_sold',0):,.0f}"
                )
                if i.get("coordinated_warning"):
                    lines.append(f"  {i['coordinated_warning']}")
                for trade in i.get("trades", [])[:3]:
                    action = "BOUGHT" if trade.get("is_buy") else "SOLD"
                    csuite = "*" if trade.get("is_csuite") else " "
                    lines.append(
                        f"  {csuite} {trade.get('date','?')} "
                        f"{trade.get('insider_name','?')} ({trade.get('insider_title','?')}) "
                        f"{action} {trade.get('shares',0):,} @ ${trade.get('price',0):.2f} "
                        f"= ${trade.get('value',0):,.0f}"
                    )
        lines.append("")

    # -- Layer 13: Congress Trades --
    lines.append("=== LAYER 13: CONGRESS TRADES ===")
    congress = data.get("congress_trades", {})
    any_ct = False
    for stock in portfolio["portfolio"]:
        t = stock["ticker"]
        ct = congress.get(t, [])
        if isinstance(ct, list) and ct:
            any_ct = True
            for trade in ct[:2]:
                relevance = "** HIGH SIGNAL **" if trade.get("relevant_committee") else ""
                lines.append(
                    f"{t}: {trade.get('name','?')} ({trade.get('chamber','?')}) "
                    f"{trade.get('transaction','?')} {trade.get('amount_range','?')} "
                    f"on {trade.get('transaction_date','?')} | "
                    f"Committee: {trade.get('committee','?')} {relevance}"
                )
    if not any_ct:
        lines.append("No recent congress trades reported.")
    lines.append("")

    # -- Layer 14: Sustainability / ESG --
    lines.append("=== LAYER 14: SUSTAINABILITY & ESG SIGNALS ===")
    esg = data.get("sustainability", {})
    any_esg = False
    for stock in portfolio["portfolio"]:
        t = stock["ticker"]
        e = esg.get(t, {})
        if e and e.get("has_esg_signal"):
            any_esg = True
            env_sig = e.get("environmental", {}).get("signal", "none")
            soc_sig = e.get("social", {}).get("signal", "none")
            gov_sig = e.get("governance", {}).get("signal", "none")
            lines.append(f"{t}: E={env_sig} | S={soc_sig} | G={gov_sig}")
            if e.get("red_flags"):
                lines.append(f"  !! RED FLAGS: {', '.join(e['red_flags'][:3])}")
            for hl in e.get("esg_headlines", [])[:2]:
                lines.append(f"  {hl}")
    global_esg = esg.get("__global_esg__", [])
    if global_esg:
        any_esg = True
        lines.append("Global ESG context:")
        for ge in global_esg[:3]:
            lines.append(f"  - {ge}")
    if not any_esg:
        lines.append("No significant ESG signals detected this cycle.")
    lines.append("")

    # -- Thesis context --
    lines.append("=== YOUR THESIS (from stocks.yaml) ===")
    for stock in portfolio["portfolio"]:
        t = stock["ticker"]
        lines.append(f"\n{t}: {stock['thesis'][:250]}")
        if stock.get("thesis_risks"):
            lines.append(f"  Risks: {' | '.join(stock['thesis_risks'][:2])}")
        if stock.get("watch_events"):
            lines.append(f"  Watch: {', '.join(stock['watch_events'])}")

        # Load living context file (appended by previous runs)
        ctx_file = f"context/{t}.md"
        if os.path.exists(ctx_file):
            with open(ctx_file, "r") as fh:
                content = fh.read()
            parts = content.split("###")
            if len(parts) > 2:
                recent = "###" + "###".join(parts[-2:])
                lines.append(f"  Recent: {recent[:300]}")

    # -- Watchlist --
    lines.append("\n=== WATCHLIST (max 5) ===")
    for w in portfolio.get("watchlist", [])[:5]:
        t = w["ticker"]
        tr = trends.get(t, {})
        spike = " **TREND SPIKE**" if tr.get("spike") else ""
        lines.append(f"{t}: {w.get('reason','')[:120]}{spike}")

    # -- Analysis request --
    lines.append("\n" + "=" * 60)
    if weekend:
        lines.append("""WEEKEND ANALYSIS REQUEST
Markets are closed. Focus on what happened this weekend for Monday open.

For each portfolio stock (2 sentences max each):
1. Any weekend development worth noting
2. THESIS STATUS: INTACT / SHAKEN / BROKEN

Then:
3. Top 3 things to watch at Monday open
4. Any urgent action needed before Monday?
5. Any watchlist entry opportunity forming?
6. NEW DISCOVERIES: 1-3 stocks worth researching that fit the investor's goal, with one-line thesis and why now. Zero is fine if nothing compelling.

Write CONTEXT_UPDATE: TICKER: [text] for any material development to log.
Keep this concise -- it's a weekend prep note, not a full analysis.""")
    else:
        lines.append(f"""ANALYSIS REQUEST -- Goal: {portfolio['meta']['investor_goal']}

For EACH portfolio stock provide:
1. THESIS STATUS: INTACT / SHAKEN / BROKEN -- one sentence, cite the specific layer
2. ACTION: Keep / Buy More / Sell -- one sentence why. Note: investor does NOT trade after hours.
3. Driving signal: which layer and what it showed

Then provide:
4. URGENT ALERT NEEDED? Yes/No -- if Yes, write the exact alert subject line on the next line
5. BIGGEST RISK right now (specific, cite layer)
6. BIGGEST OPPORTUNITY right now (with entry logic)
7. WATCHLIST: for each watchlist ticker, is now a good entry? Cite data.
8. NEW DISCOVERIES: suggest 1-3 stocks NOT in the portfolio or watchlist that fit the investor's
   goal ({portfolio['meta']['investor_goal']}). For each, give ticker, one-line thesis,
   and why NOW based on signals you saw in today's data (sector momentum, macro setup, etc).
   Only suggest if you have genuine conviction -- zero is fine.
   The watchlist is capped at 5. If it's full and a new discovery is stronger than an existing
   watchlist entry, recommend replacing the weakest one.
9. SUSTAINABILITY: Flag any ESG concerns from Layer 14 -- governance red flags (fraud lawsuits,
   auditor changes, insider selling patterns), environmental risks (regulatory, climate exposure),
   or social controversies that could impact thesis or valuation. Only mention if material.

Write CONTEXT_UPDATE: TICKER: [1-2 sentence update] for any ticker with material new development.
These get appended to the living context log for that ticker.

Be direct and specific. Use $ and % numbers. Cite which data layer drove each call.
No fluff. If a layer had an error, note it and continue.""")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Context file management -- living thesis evolution logs
# ---------------------------------------------------------------------------

def update_context_files(claude_response, portfolio):
    """Parse CONTEXT_UPDATE: TICKER: text and append to per-stock context files."""
    os.makedirs("context", exist_ok=True)
    for line in claude_response.split("\n"):
        if line.startswith("CONTEXT_UPDATE:"):
            try:
                rest = line[len("CONTEXT_UPDATE:"):].strip()
                parts = rest.split(":", 1)
                if len(parts) == 2:
                    ticker = parts[0].strip().upper()
                    update = parts[1].strip()
                    ctx_file = f"context/{ticker}.md"
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

                    if not os.path.exists(ctx_file):
                        thesis = next(
                            (s["thesis"] for s in portfolio["portfolio"] if s["ticker"] == ticker),
                            "No thesis recorded.",
                        )
                        with open(ctx_file, "w") as fh:
                            fh.write(f"# {ticker} -- Living Context Log\n\n")
                            fh.write(f"## Original thesis\n{thesis}\n\n")
                            fh.write("## Thesis evolution\n\n")

                    with open(ctx_file, "a") as fh:
                        fh.write(f"\n### {timestamp}\n{update}\n")
                    print(f"  [ok] context/{ticker}.md updated")
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------

def call_claude(prompt):
    """Send the assembled prompt to Claude and return the response text."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def should_alert(response):
    """Check if Claude flagged an urgent alert."""
    return "URGENT ALERT NEEDED? YES" in response.upper()


def extract_subject(response):
    """Extract alert subject line from Claude's response."""
    date_str = datetime.now().strftime("%b %d")
    lines = response.split("\n")
    for i, line in enumerate(lines):
        if "urgent alert needed? yes" in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                s = lines[j].strip().strip('"').strip("'")
                if s and "urgent alert" not in s.lower():
                    return f"[ALERT] {date_str} -- {s}"
    return f"[ALERT] {date_str} -- Portfolio Alert -- Review Recommended"


# ---------------------------------------------------------------------------
# Run logging
# ---------------------------------------------------------------------------

def log_run(data, response, alert_sent):
    """Append run summary to logs/stock_analysis.jsonl."""
    os.makedirs("logs", exist_ok=True)
    prices = data.get("prices", {})
    entry = {
        "timestamp": datetime.now().isoformat(),
        "alert_sent": alert_sent,
        "weekend": is_weekend(),
        "prices": {
            k: v.get("price")
            for k, v in prices.items()
            if not k.startswith("__") and isinstance(v, dict) and not v.get("error")
        },
        "pnl_pct": prices.get("__portfolio_pnl_pct__", 0),
        "response": response[:600],
    }
    with open("logs/stock_analysis.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run(test_mode=False, digest_only=False):
    """Execute one full analysis cycle."""
    print(f"\n{'=' * 60}")
    print(f"  thesis-engine -- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")

    portfolio = load_portfolio()
    weekend = is_weekend()
    tickers = [s["ticker"] for s in portfolio["portfolio"]]
    print(f"  Mode: {'WEEKEND' if weekend else 'WEEKDAY'} | Tickers: {', '.join(tickers)}")

    # Fetch all data layers in parallel
    data = fetch_all_data(portfolio, weekend=weekend)

    # Layer 14: extract sustainability signals from already-fetched data
    data["sustainability"] = extract_sustainability_signals(data, portfolio)
    print("    [ok] sustainability (ESG signal extraction)")

    # Build prompt and call Claude
    print("  Calling Claude...")
    prompt = build_prompt(portfolio, data, weekend=weekend)
    response = call_claude(prompt)
    print(f"  [ok] Claude responded ({len(response)} chars)")

    # Update living context files
    update_context_files(response, portfolio)

    # Determine if alert needed
    alert_sent = False
    eod = is_eod()
    sun_prep = is_sunday_prep()

    if test_mode:
        print("\n  TEST MODE -- Claude's response:")
        print("  " + "\n  ".join(response.split("\n")))
        print("\n  [No alerts sent in test mode]")
    else:
        # Urgent intraday alert
        if not digest_only and not weekend and should_alert(response):
            subject = extract_subject(response)
            send_urgent_alert(subject, response, portfolio, data)
            log_notification("urgent", subject, response, data)
            alert_sent = True

        # Daily digest (4pm ET) or weekend prep (Sunday 6pm)
        if eod or sun_prep or (weekend and datetime.now().hour in [9, 21]):
            prefix = "Weekend Prep" if weekend else "Daily Digest"
            pnl = data.get("prices", {}).get("__portfolio_pnl_pct__", 0)
            subj = f"{prefix} -- {datetime.now().strftime('%b %d')} | Portfolio {pnl:+.1f}%"
            send_digest(subj, response, portfolio, data)
            log_notification("digest", subj, response, data)
            alert_sent = True

    log_run(data, response, alert_sent)
    print(f"\n  [ok] Done -- {datetime.now().strftime('%H:%M:%S')}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="thesis-engine")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--loop", action="store_true", help="Run hourly (local)")
    parser.add_argument("--test", action="store_true", help="No alerts, print output only")
    parser.add_argument("--digest-only", action="store_true", help="Skip urgent alerts")
    parser.add_argument("--interval", type=int, default=60, help="Loop interval in minutes")
    args = parser.parse_args()

    if args.loop:
        print(f"Starting loop (every {args.interval} min). Ctrl+C to stop.")
        run(test_mode=args.test, digest_only=args.digest_only)
        schedule.every(args.interval).minutes.do(
            run, test_mode=args.test, digest_only=args.digest_only,
        )
        while True:
            schedule.run_pending()
            time.sleep(30)
    else:
        run(test_mode=args.test, digest_only=args.digest_only)
