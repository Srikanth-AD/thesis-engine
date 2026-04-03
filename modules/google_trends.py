"""
Layer 9 -- Google Trends

Search volume spikes often precede price moves.
Rising attention could be positive OR negative -- the LLM interprets in context.
Free, no API key. Uses the unofficial pytrends library.
"""
import time

try:
    from pytrends.request import TrendReq
    PYTRENDS_AVAILABLE = True
except ImportError:
    PYTRENDS_AVAILABLE = False


def fetch_google_trends(tickers):
    """
    Fetch Google Trends interest-over-time data for a list of tickers.

    Processes tickers in batches of 4 (pytrends limit is 5, leaving headroom).
    Computes 7-day, 30-day, and 90-day averages plus spike detection.

    Args:
        tickers: List of ticker symbol strings.

    Returns:
        Dict keyed by ticker with:
        - score:      Current interest score (0-100).
        - avg_7d:     7-day average interest.
        - avg_30d:    30-day average interest.
        - avg_90d:    90-day average interest.
        - change_pct: Percent change (7d vs 30d).
        - spike:      True if 7d avg > 2x the 90d avg.
        - spike_mult: Multiplier of 7d avg over 90d avg.
    """
    if not PYTRENDS_AVAILABLE:
        return {t: {"error": "pytrends not installed"} for t in tickers}

    results = {}

    try:
        pytrends = TrendReq(hl="en-US", tz=360, timeout=(10, 25))

        # Process in batches of 4
        for i in range(0, len(tickers), 4):
            batch = tickers[i:i + 4]
            try:
                pytrends.build_payload(batch, timeframe="today 3-m", geo="US")
                data = pytrends.interest_over_time()

                if data is not None and not data.empty:
                    for ticker in batch:
                        if ticker in data.columns:
                            series    = data[ticker]
                            score_now = int(series.iloc[-1])
                            avg_30d   = float(series.tail(30).mean())
                            avg_7d    = float(series.tail(7).mean())
                            avg_90d   = float(series.mean())

                            # Spike detection: current 7d avg vs 90d avg
                            spike_mult = (avg_7d / avg_90d) if avg_90d > 0 else 1.0
                            change_pct = ((avg_7d - avg_30d) / avg_30d * 100) if avg_30d > 0 else 0

                            results[ticker] = {
                                "score":      score_now,
                                "avg_7d":     round(avg_7d, 1),
                                "avg_30d":    round(avg_30d, 1),
                                "avg_90d":    round(avg_90d, 1),
                                "change_pct": round(change_pct, 0),
                                "spike":      spike_mult > 2.0,
                                "spike_mult": round(spike_mult, 2),
                            }
                        else:
                            results[ticker] = {"score": 0, "spike": False, "change_pct": 0}
                else:
                    for ticker in batch:
                        results[ticker] = {"error": "no trend data"}

                time.sleep(2)  # Google is aggressive about rate limiting

            except Exception as e:
                for ticker in batch:
                    results[ticker] = {"error": str(e)}
                time.sleep(5)  # Back off on error

    except Exception as e:
        for t in tickers:
            if t not in results:
                results[t] = {"error": str(e)}

    return results
