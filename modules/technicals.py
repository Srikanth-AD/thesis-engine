"""
Layer 3 — Technical Indicators

20+ indicators across 6 categories:
  - Trend: EMA crossover (9/21), MACD, ADX, Ichimoku Cloud
  - Momentum: RSI (14), Stochastic Oscillator, Williams %R
  - Volume: OBV, VWAP, Accumulation/Distribution
  - Volatility: Bollinger Bands, ATR, Keltner Channels
  - Support/Resistance: Fibonacci retracement, Pivot Points
  - Composite: 8-indicator bullish/bearish scoring (0-100%)

Uses 90-day candle history from Finnhub + the 'ta' library.
"""
import os
import time

import pandas as pd
import requests

try:
    import ta
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
BASE = "https://finnhub.io/api/v1"


def _get_candles(ticker, resolution="D", days_back=90):
    """Fetch OHLCV candle data from Finnhub."""
    import time as t
    now = int(t.time())
    from_ts = now - (days_back * 24 * 3600)
    params = {
        "symbol": ticker,
        "resolution": resolution,
        "from": from_ts,
        "to": now,
        "token": FINNHUB_KEY,
    }
    try:
        r = requests.get(f"{BASE}/stock/candle", params=params, timeout=15)
        data = r.json()
        if data.get("s") != "ok" or not data.get("c"):
            return None
        return pd.DataFrame({
            "open": data["o"],
            "high": data["h"],
            "low": data["l"],
            "close": data["c"],
            "volume": data["v"],
        })
    except Exception:
        return None


def _fib_levels(df):
    """Fibonacci retracement from recent 60-day high/low."""
    window = df.tail(60)
    high = float(window["high"].max())
    low = float(window["low"].min())
    diff = high - low
    if diff == 0:
        return None
    price = float(df["close"].iloc[-1])
    levels = {
        "high": round(high, 2),
        "0.236": round(high - 0.236 * diff, 2),
        "0.382": round(high - 0.382 * diff, 2),
        "0.500": round(high - 0.500 * diff, 2),
        "0.618": round(high - 0.618 * diff, 2),
        "low": round(low, 2),
    }
    nearest = min(levels.items(), key=lambda x: abs(x[1] - price))
    return f"Near {nearest[0]} (${nearest[1]}) | Range ${low:.2f}-${high:.2f}"


def _pivot_points(df):
    """Classic pivot points from previous day's OHLC."""
    prev = df.iloc[-2]
    h, l, c = float(prev["high"]), float(prev["low"]), float(prev["close"])
    pivot = (h + l + c) / 3
    r1 = 2 * pivot - l
    s1 = 2 * pivot - h
    price = float(df["close"].iloc[-1])
    if price > r1:
        pos = "above R1 (bullish breakout)"
    elif price > pivot:
        pos = "above pivot (bullish)"
    elif price > s1:
        pos = "below pivot (bearish)"
    else:
        pos = "below S1 (bearish breakdown)"
    return f"{pos} | P:${pivot:.2f} S1:${s1:.2f} R1:${r1:.2f}"


def calculate_technicals(tickers):
    """
    Calculate all technical indicators for each ticker.

    Returns dict keyed by ticker with trend, momentum, volume,
    volatility, support/resistance, and composite score.
    """
    results = {}

    if not TA_AVAILABLE:
        return {t: {"error": "ta not installed -- run: pip install ta"} for t in tickers}

    for ticker in tickers:
        try:
            df = _get_candles(ticker)
            if df is None or len(df) < 26:
                results[ticker] = {"error": "insufficient candle data"}
                time.sleep(0.15)
                continue

            close = df["close"]
            high = df["high"]
            low = df["low"]
            volume = df["volume"]
            price = float(close.iloc[-1])

            # -- TREND --

            # EMA crossover (9/21)
            e9 = float(ta.trend.EMAIndicator(close=close, window=9).ema_indicator().iloc[-1])
            e21 = float(ta.trend.EMAIndicator(close=close, window=21).ema_indicator().iloc[-1])
            ema_trend = "bullish (EMA9>EMA21)" if e9 > e21 else "bearish (EMA9<EMA21)"

            # MACD
            macd_ind = ta.trend.MACD(close=close)
            macd_hist = float(macd_ind.macd_diff().iloc[-1])
            macd_prev = float(macd_ind.macd_diff().iloc[-2])
            if macd_hist > 0 and macd_prev <= 0:
                macd_signal = "bullish crossover"
            elif macd_hist < 0 and macd_prev >= 0:
                macd_signal = "bearish crossover"
            elif macd_hist > 0:
                macd_signal = "bullish"
            else:
                macd_signal = "bearish"

            # ADX — trend strength and direction
            adx_ind = ta.trend.ADXIndicator(high=high, low=low, close=close, window=14)
            adx_val = round(float(adx_ind.adx().iloc[-1]), 1)
            plus_di = float(adx_ind.adx_pos().iloc[-1])
            minus_di = float(adx_ind.adx_neg().iloc[-1])
            if adx_val < 20:
                adx_label = f"{adx_val} (no trend)"
            elif adx_val < 40:
                direction = "up" if plus_di > minus_di else "down"
                adx_label = f"{adx_val} (trending {direction})"
            else:
                direction = "up" if plus_di > minus_di else "down"
                adx_label = f"{adx_val} (strong trend {direction})"

            # Ichimoku Cloud
            ichi = ta.trend.IchimokuIndicator(high=high, low=low)
            span_a = float(ichi.ichimoku_a().iloc[-1])
            span_b = float(ichi.ichimoku_b().iloc[-1])
            cloud_top = max(span_a, span_b)
            cloud_bottom = min(span_a, span_b)
            if price > cloud_top:
                ichi_signal = "above cloud (bullish)"
            elif price < cloud_bottom:
                ichi_signal = "below cloud (bearish)"
            else:
                ichi_signal = "inside cloud (neutral)"

            # -- MOMENTUM --

            # RSI (14)
            rsi_val = round(float(
                ta.momentum.RSIIndicator(close=close, window=14).rsi().iloc[-1]
            ), 1)
            if rsi_val > 70:
                rsi_label = f"{rsi_val} (overbought)"
            elif rsi_val < 30:
                rsi_label = f"{rsi_val} (oversold)"
            else:
                rsi_label = str(rsi_val)

            # Stochastic Oscillator
            stoch = ta.momentum.StochasticOscillator(high=high, low=low, close=close)
            stoch_k = round(float(stoch.stoch().iloc[-1]), 1)
            stoch_d = round(float(stoch.stoch_signal().iloc[-1]), 1)
            if stoch_k > 80:
                stoch_label = f"%K:{stoch_k} %D:{stoch_d} (overbought)"
            elif stoch_k < 20:
                stoch_label = f"%K:{stoch_k} %D:{stoch_d} (oversold)"
            elif stoch_k > stoch_d:
                stoch_label = f"%K:{stoch_k} %D:{stoch_d} (bullish cross)"
            else:
                stoch_label = f"%K:{stoch_k} %D:{stoch_d}"

            # Williams %R
            wr = round(float(
                ta.momentum.WilliamsRIndicator(high=high, low=low, close=close).williams_r().iloc[-1]
            ), 1)
            if wr > -20:
                wr_label = f"{wr} (overbought)"
            elif wr < -80:
                wr_label = f"{wr} (oversold)"
            else:
                wr_label = str(wr)

            # -- VOLUME --

            vol_ratio = round(float(volume.iloc[-1]) / float(volume.tail(20).mean()), 2)

            # OBV trend (5-day comparison)
            obv = ta.volume.OnBalanceVolumeIndicator(close=close, volume=volume).on_balance_volume()
            obv_now = float(obv.iloc[-1])
            obv_prev = float(obv.iloc[-6])
            if obv_now > obv_prev * 1.02:
                obv_trend = "rising (accumulation)"
            elif obv_now < obv_prev * 0.98:
                obv_trend = "falling (distribution)"
            else:
                obv_trend = "flat"

            # VWAP approximation from daily data
            typical_price = (high + low + close) / 3
            vwap_val = round(float((typical_price * volume).tail(5).sum() / volume.tail(5).sum()), 2)
            vwap_label = f"${vwap_val}"
            if price > vwap_val:
                vwap_label += " (price above -- bullish)"
            else:
                vwap_label += " (price below -- bearish)"

            # Accumulation/Distribution
            ad = ta.volume.AccDistIndexIndicator(high=high, low=low, close=close, volume=volume)
            ad_line = ad.acc_dist_index()
            ad_now = float(ad_line.iloc[-1])
            ad_prev = float(ad_line.iloc[-6])
            ad_trend = "rising (buying pressure)" if ad_now > ad_prev else "falling (selling pressure)"

            # -- VOLATILITY --

            # ATR (14)
            atr_val = round(float(
                ta.volatility.AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range().iloc[-1]
            ), 2)
            atr_pct = round(atr_val / price * 100, 1)

            # Bollinger Bands (20, 2)
            bb = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
            bb_hi = float(bb.bollinger_hband().iloc[-1])
            bb_lo = float(bb.bollinger_lband().iloc[-1])
            bb_mi = float(bb.bollinger_mavg().iloc[-1])
            bw = bb_hi - bb_lo
            if bw > 0:
                pct = (price - bb_lo) / bw
                if pct > 0.85:
                    bb_pos = f"upper band ({pct:.0%}) extended"
                elif pct < 0.15:
                    bb_pos = f"lower band ({pct:.0%}) oversold"
                else:
                    bb_pos = f"mid band ({pct:.0%})"
                if bw / bb_mi < 0.05:
                    bb_pos += " [SQUEEZE]"
            else:
                bb_pos = "N/A"

            # Keltner Channels + BB squeeze detection
            kc = ta.volatility.KeltnerChannel(high=high, low=low, close=close)
            kc_hi = float(kc.keltner_channel_hband().iloc[-1])
            kc_lo = float(kc.keltner_channel_lband().iloc[-1])
            if price > kc_hi:
                kc_label = "above upper (breakout)"
            elif price < kc_lo:
                kc_label = "below lower (breakdown)"
            else:
                kc_label = "inside channel"
            # BB inside Keltner = low volatility squeeze, breakout imminent
            if bb_hi < kc_hi and bb_lo > kc_lo:
                kc_label += " [BB SQUEEZE -- breakout imminent]"

            # -- SUPPORT/RESISTANCE --

            fib_label = _fib_levels(df)
            pivot_label = _pivot_points(df)

            # -- COMPOSITE SIGNAL --
            # Score 8 indicators as bullish or bearish

            bullish = 0
            bearish = 0
            if e9 > e21:
                bullish += 1
            else:
                bearish += 1
            if macd_hist > 0:
                bullish += 1
            else:
                bearish += 1
            if rsi_val > 50:
                bullish += 1
            else:
                bearish += 1
            if price > cloud_top:
                bullish += 1
            elif price < cloud_bottom:
                bearish += 1
            if obv_now > obv_prev:
                bullish += 1
            else:
                bearish += 1
            if price > vwap_val:
                bullish += 1
            else:
                bearish += 1
            if stoch_k > stoch_d:
                bullish += 1
            else:
                bearish += 1

            total = bullish + bearish
            score = round(bullish / total * 100) if total > 0 else 50
            if score >= 70:
                overall = f"{score}% bullish -- strong buy signals"
            elif score >= 55:
                overall = f"{score}% bullish -- leaning buy"
            elif score <= 30:
                overall = f"{score}% bullish -- strong sell signals"
            elif score <= 45:
                overall = f"{score}% bullish -- leaning sell"
            else:
                overall = f"{score}% -- mixed/neutral"

            results[ticker] = {
                "ema_trend": ema_trend,
                "macd_signal": macd_signal,
                "macd_histogram": round(macd_hist, 4),
                "adx": adx_label,
                "ichimoku": ichi_signal,
                "rsi": rsi_label,
                "stochastic": stoch_label,
                "williams_r": wr_label,
                "volume_vs_avg": vol_ratio,
                "obv_trend": obv_trend,
                "vwap": vwap_label,
                "acc_dist": ad_trend,
                "atr": f"${atr_val} ({atr_pct}% of price)",
                "bb_position": bb_pos,
                "keltner": kc_label,
                "fibonacci": fib_label,
                "pivot_points": pivot_label,
                "technical_score": overall,
            }
            time.sleep(0.15)

        except Exception as e:
            results[ticker] = {"error": str(e)}

    return results
