"""
Layer 4 — Macro Data

VIX, oil, Treasury yields, DXY via Yahoo Finance public API.
CPI, unemployment via Bureau of Labor Statistics (free, 25 req/day).
Fed funds rate via Finnhub. No FRED dependency.
"""
import os
from datetime import datetime

import requests

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")

# Yahoo Finance tickers (public chart API, no key needed)
YF_TICKERS = {
    "vix": "^VIX",
    "oil_wti": "CL=F",
    "treasury_10y": "^TNX",
    "treasury_2y": "2YY=F",
    "dxy": "DX-Y.NYB",
}

# BLS public API (free, no key required, 25 req/day)
BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
BLS_SERIES = {
    "cpi": "CUSR0000SA0",
    "unemployment": "LNS14000000",
}

YF_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _fetch_yf(ticker):
    """Get latest + previous close from Yahoo Finance chart API."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        r = requests.get(url, params={"range": "5d", "interval": "1d"},
                         headers=YF_HEADERS, timeout=10)
        data = r.json()
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        valid = [c for c in closes if c is not None]
        if len(valid) >= 2:
            return round(valid[-1], 2), round(valid[-2], 2)
        elif valid:
            return round(valid[-1], 2), None
    except Exception:
        pass
    return None, None


def _fetch_bls(series_id):
    """Get latest 2 observations from BLS."""
    try:
        year = datetime.now().year
        r = requests.post(BLS_URL, json={
            "seriesid": [series_id],
            "startyear": str(year - 1),
            "endyear": str(year),
        }, timeout=10)
        values = r.json()["Results"]["series"][0]["data"]
        if len(values) >= 2:
            return float(values[0]["value"]), float(values[1]["value"])
        elif values:
            return float(values[0]["value"]), None
    except Exception:
        pass
    return None, None


def _fetch_fed_rate():
    """Get effective federal funds rate from Finnhub economic data."""
    try:
        r = requests.get("https://finnhub.io/api/v1/economic", params={
            "code": "MA-USA-656880",
            "token": FINNHUB_KEY,
        }, timeout=10)
        data = r.json().get("data", [])
        if len(data) >= 2:
            return round(float(data[-1]["value"]), 2), round(float(data[-2]["value"]), 2)
        elif data:
            return round(float(data[-1]["value"]), 2), None
    except Exception:
        pass
    return None, None


def _trend(current, previous):
    """Simple trend label from two observations."""
    if current is None or previous is None:
        return "N/A"
    try:
        c, p = float(current), float(previous)
        if c > p:
            return "rising"
        elif c < p:
            return "falling"
        return "flat"
    except Exception:
        return "N/A"


def fetch_macro():
    """
    Fetch macro indicators from Yahoo Finance, BLS, and Finnhub.

    Returns flat dict with current values, trends, and yield curve analysis.
    """
    result = {}
    try:
        for name, ticker in YF_TICKERS.items():
            current, prev = _fetch_yf(ticker)
            result[name] = current
            result[f"{name}_trend"] = _trend(current, prev)

        for name, series_id in BLS_SERIES.items():
            current, prev = _fetch_bls(series_id)
            result[name] = current
            result[f"{name}_trend"] = _trend(current, prev)

        fed_cur, fed_prev = _fetch_fed_rate()
        result["fed_rate"] = fed_cur
        result["fed_rate_trend"] = _trend(fed_cur, fed_prev)

        # Yield curve spread (10y - 2y)
        t10 = result.get("treasury_10y")
        t2 = result.get("treasury_2y")
        if t10 and t2:
            result["yield_spread"] = round(t10 - t2, 2)
            result["yield_curve"] = "normal" if t10 > t2 else "inverted"

        result["timestamp"] = datetime.now().isoformat()

    except Exception as e:
        result["error"] = str(e)

    return result
