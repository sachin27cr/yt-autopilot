"""Binance USDT-M futures public data (no API key needed).

Note: Binance returns HTTP 451 for US IPs, so run the bot in an EU/Asia region.
"""
import pandas as pd
import requests

from config import BINANCE_FAPI

_S = requests.Session()
_S.headers["User-Agent"] = "yt-autopilot/1.0"


def _get(path: str, params: dict):
    r = _S.get(BINANCE_FAPI + path, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def _now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _period(days: int) -> tuple[str, int]:
    """Pick a bar size so we stay inside Binance's 500-row / 30-day limits."""
    if days <= 3:
        return "1h", days * 24
    return "4h", min(500, days * 6)


def klines(symbol: str, days: int = 7) -> pd.DataFrame:
    interval, limit = ("1h", days * 24) if days <= 3 else (("4h", days * 6) if days <= 60 else ("1d", days))
    data = _get("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": min(1500, limit)})
    df = pd.DataFrame(data, columns=["t", "o", "h", "l", "c", "v", "ct", "qv", "n", "tb", "tq", "x"])
    df["t"] = pd.to_datetime(df["t"], unit="ms", utc=True)
    for col in ["o", "h", "l", "c", "v"]:
        df[col] = df[col].astype(float)
    return df[["t", "o", "h", "l", "c", "v"]]


def funding(symbol: str, days: int = 7) -> pd.DataFrame:
    data = _get("/fapi/v1/fundingRate", {"symbol": symbol, "limit": min(1000, days * 3 + 6)})
    df = pd.DataFrame(data)
    df["t"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df["rate_pct"] = df["fundingRate"].astype(float) * 100
    return df[df["t"] >= _now() - pd.Timedelta(days=days)][["t", "rate_pct"]]


def open_interest(symbol: str, days: int = 7) -> pd.DataFrame:
    days = min(days, 30)
    period, limit = _period(days)
    data = _get("/futures/data/openInterestHist", {"symbol": symbol, "period": period, "limit": limit})
    df = pd.DataFrame(data)
    df["t"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["oi_usd"] = df["sumOpenInterestValue"].astype(float)
    return df[["t", "oi_usd"]]


def long_short(symbol: str, days: int = 7) -> pd.DataFrame:
    days = min(days, 30)
    period, limit = _period(days)
    data = _get("/futures/data/globalLongShortAccountRatio", {"symbol": symbol, "period": period, "limit": limit})
    df = pd.DataFrame(data)
    df["t"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["ratio"] = df["longShortRatio"].astype(float)
    return df[["t", "ratio"]]


def snapshot(symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"), days: int = 7) -> dict:
    """Numbers the script writer is allowed to quote."""
    out = {}
    for sym in symbols:
        row = {}
        try:
            k = klines(sym, days)
            first, last = k["o"].iloc[0], k["c"].iloc[-1]
            row.update(
                price=round(last, 4),
                change_pct=round((last / first - 1) * 100, 2),
                high=round(k["h"].max(), 4),
                low=round(k["l"].min(), 4),
            )
        except Exception as e:  # noqa: BLE001
            row["price_error"] = str(e)[:120]
        try:
            f = funding(sym, days)
            row.update(funding_avg_pct=round(f["rate_pct"].mean(), 4), funding_last_pct=round(f["rate_pct"].iloc[-1], 4))
        except Exception as e:  # noqa: BLE001
            row["funding_error"] = str(e)[:120]
        try:
            oi = open_interest(sym, days)
            row.update(
                oi_usd_bn=round(oi["oi_usd"].iloc[-1] / 1e9, 3),
                oi_change_pct=round((oi["oi_usd"].iloc[-1] / oi["oi_usd"].iloc[0] - 1) * 100, 2),
            )
        except Exception as e:  # noqa: BLE001
            row["oi_error"] = str(e)[:120]
        try:
            ls = long_short(sym, days)
            row["long_short_ratio"] = round(ls["ratio"].iloc[-1], 3)
        except Exception as e:  # noqa: BLE001
            row["ls_error"] = str(e)[:120]
        out[sym] = row
    return out


def snapshot_text(snap: dict, days: int = 7) -> str:
    lines = [f"MARKET DATA (Binance USDT-M futures, last {days} days, as of {_now():%Y-%m-%d %H:%M} UTC):"]
    for sym, r in snap.items():
        lines.append(f"- {sym}: " + ", ".join(f"{k}={v}" for k, v in r.items()))
    return "\n".join(lines)
