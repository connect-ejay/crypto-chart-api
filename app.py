from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import urllib.request
import json
import time
import math
from datetime import datetime
from io import BytesIO

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D


app = FastAPI(title="Crypto TA Candlestick Renderer")


class ChartRequest(BaseModel):
    symbol: str
    name: str | None = None
    risk: str | None = "Medium"
    reason: str | None = "Technical setup generated from market data."


def fmt(n, digits=4):
    try:
        return f"{float(n):,.{digits}f}".rstrip("0").rstrip(".")
    except Exception:
        return "n/a"


def fetch_klines(symbol: str):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol.upper()}&interval=1h&limit=180"
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def ema(values, period):
    if not values:
        return []
    k = 2 / (period + 1)
    out = []
    prev = values[0]
    for v in values:
        prev = v * k + prev * (1 - k)
        out.append(prev)
    return out


def rsi(values, period=14):
    if len(values) <= period:
        return 50
    gains = 0
    losses = 0
    for i in range(1, period + 1):
        diff = values[i] - values[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(values)):
        diff = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(diff, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-diff, 0)) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(values, fast=12, slow=26, signal=9):
    ef = ema(values, fast)
    es = ema(values, slow)
    line = [a - b for a, b in zip(ef, es)]
    sig = ema(line, signal)
    hist = [a - b for a, b in zip(line, sig)]
    return line, sig, hist


def render_chart(req: ChartRequest) -> bytes:
    symbol = req.symbol.upper().strip()
    if not symbol.endswith("USDT"):
        symbol = symbol + "USDT"

    name = req.name or symbol.replace("USDT", "")
    risk = req.risk or "Medium"
    reason = req.reason or "Technical setup generated from market data."

    raw = fetch_klines(symbol)

    if not isinstance(raw, list) or len(raw) < 80:
        raise HTTPException(status_code=400, detail="Not enough Binance candle data")

    raw = raw[-120:]
    opens = [float(k[1]) for k in raw]
    highs = [float(k[2]) for k in raw]
    lows = [float(k[3]) for k in raw]
    closes = [float(k[4]) for k in raw]
    volumes = [float(k[5]) for k in raw]
    times = [datetime.fromtimestamp(int(k[0]) / 1000) for k in raw]
    x = list(range(len(closes)))

    last_close = closes[-1]
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    rsi14 = rsi(closes, 14)
    macd_line, signal_line, hist = macd(closes)

    support = min(lows[-45:])
    resistance = max(highs[-45:])
    entry = last_close
    tp1 = last_close * 1.035
    tp2 = last_close * 1.07
    sl = last_close * 0.96

    score = 0
    if last_close > ema20[-1]:
        score += 15
    if ema20[-1] > ema50[-1]:
        score += 20
    if last_close > ema50[-1]:
        score += 15
    if 45 < rsi14 < 68:
        score += 20
    if macd_line[-1] > signal_line[-1]:
        score += 20
    if volumes[-1] > (sum(volumes[-20:]) / 20):
        score += 10

    trend = "Sideways / unclear"
    ta_bias = "WAIT"
    if score >= 75:
        trend = "Bullish continuation"
        ta_bias = "LONG WATCH"
    elif score >= 55:
        trend = "Possible bullish setup"
        ta_bias = "WATCHLIST"
    elif last_close < ema20[-1] and ema20[-1] < ema50[-1] and rsi14 < 50:
        trend = "Bearish pressure"
        ta_bias = "SHORT WATCH / AVOID LONG"

    if rsi14 >= 70:
        trend = "Overbought"
        ta_bias = "WAIT FOR PULLBACK"
    if rsi14 <= 30:
        trend = "Oversold"
        ta_bias = "WATCH REVERSAL ONLY"

    fig, ax = plt.subplots(figsize=(14, 8), dpi=140)
    fig.patch.set_facecolor("#0b0f14")
    ax.set_facecolor("#0b0f14")

    candle_width = 0.62
    for i, (o, h, l, c) in enumerate(zip(opens, highs, lows, closes)):
        color = "#00c2a8" if c >= o else "#ef4444"
        ax.vlines(i, l, h, color=color, linewidth=1.0, alpha=0.95)
        body_low = min(o, c)
        body_height = abs(c - o)
        if body_height == 0:
            body_height = max((max(highs) - min(lows)) * 0.001, 0.0000001)
        ax.add_patch(
            Rectangle(
                (i - candle_width / 2, body_low),
                candle_width,
                body_height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.8,
                alpha=0.95,
            )
        )

    future_start = len(x) - 1
    future_end = len(x) + 32

    ax.add_patch(
        Rectangle(
            (future_start, entry),
            future_end - future_start,
            tp2 - entry,
            facecolor="#64748b",
            edgecolor="#94a3b8",
            alpha=0.24,
            linewidth=1.0,
        )
    )
    ax.add_patch(
        Rectangle(
            (future_start, sl),
            future_end - future_start,
            entry - sl,
            facecolor="#7f1d1d",
            edgecolor="#ef4444",
            alpha=0.42,
            linewidth=1.0,
        )
    )

    ax.axhline(resistance, color="#e5e7eb", linewidth=1.2, alpha=0.88)
    ax.axhline(support, color="#94a3b8", linewidth=1.0, alpha=0.75)
    ax.axhline(entry, color="#a855f7", linewidth=1.2, alpha=0.9)
    ax.axhline(tp1, color="#22c55e", linewidth=1.0, alpha=0.9)
    ax.axhline(tp2, color="#16a34a", linewidth=1.0, alpha=0.9)
    ax.axhline(sl, color="#ef4444", linewidth=1.2, alpha=0.9)

    low_slice = lows[: max(10, int(len(lows) * 0.65))]
    start_low = min(low_slice)
    start_idx = lows.index(start_low)
    slope = (last_close - start_low) / max(1, (len(closes) - 1) - start_idx)
    end_idx = len(closes) + 14
    ax.plot(
        [start_idx, end_idx],
        [start_low, start_low + slope * (end_idx - start_idx)],
        color="#d1d5db",
        linewidth=1.4,
        alpha=0.9,
    )

    right_x = future_end + 1
    label_style = dict(fontsize=8, color="white", va="center", ha="left", fontweight="bold")
    ax.text(right_x, resistance, f"RES {fmt(resistance)}", **label_style)
    ax.text(right_x, entry, f"ENTRY {fmt(entry)}", **label_style)
    ax.text(right_x, tp1, f"TP1 {fmt(tp1)}", **label_style)
    ax.text(right_x, tp2, f"TP2 {fmt(tp2)}", **label_style)
    ax.text(right_x, sl, f"SL {fmt(sl)}", **label_style)
    ax.text(right_x, support, f"SUP {fmt(support)}", **label_style)

    ax.grid(True, color="white", alpha=0.06, linewidth=0.7)
    ax.tick_params(colors="#94a3b8", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#1f2937")

    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")

    tick_positions = list(range(0, len(times), max(1, len(times) // 8)))
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(
        [times[i].strftime("%m/%d %H:%M") for i in tick_positions],
        rotation=0,
        ha="center",
        color="#94a3b8",
    )

    y_min = min(min(lows), sl) * 0.985
    y_max = max(max(highs), tp2) * 1.015
    ax.set_ylim(y_min, y_max)
    ax.set_xlim(0, future_end + 11)

    ax.set_title(
        f"{symbol} · 1H · Automated TradingView-Style TA",
        color="#f8fafc",
        fontsize=14,
        loc="left",
        pad=12,
    )
    ax.text(
        0.01,
        0.96,
        f"Bias: {ta_bias} | Score: {score}/100 | RSI: {fmt(rsi14,2)} | MACD: {'Bullish' if macd_line[-1] > signal_line[-1] else 'Bearish'}",
        transform=ax.transAxes,
        color="#cbd5e1",
        fontsize=9,
        va="top",
    )

    handles = [
        Line2D([0], [0], color="#d1d5db", lw=1.4, label="Trendline"),
        Line2D([0], [0], color="#a855f7", lw=1.2, label="Entry"),
        Line2D([0], [0], color="#22c55e", lw=1.2, label="TP"),
        Line2D([0], [0], color="#ef4444", lw=1.2, label="SL"),
    ]
    leg = ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0, 0.91), frameon=False, fontsize=8)
    for text in leg.get_texts():
        text.set_color("#cbd5e1")

    fig.text(0.012, 0.015, "Generated by crypto-chart-api", color="#64748b", fontsize=8)

    buffer = BytesIO()
    plt.tight_layout()
    plt.savefig(buffer, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    return buffer.read()


@app.get("/")
def home():
    return {"status": "ok", "message": "Crypto TA Chart API is running. POST /render-chart"}


@app.post("/render-chart")
def render_chart_endpoint(req: ChartRequest):
    png = render_chart(req)
    return Response(content=png, media_type="image/png")
