"""Scene visuals: live-data charts, text cards, timelines and stock footage."""
import hashlib
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import requests  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import market  # noqa: E402
from channels import Channel  # noqa: E402
from config import PEXELS_API_KEY  # noqa: E402
from utils import font, log, wrap  # noqa: E402

GREEN, RED, MUTED = "#22c55e", "#ef4444", "#8b95a5"


# ----------------------------------------------------------------------------- charts
def _chart_canvas(W: int, H: int, ch: Channel):
    s = min(W, H) / 1080
    portrait = H > W
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=ch.background)
    # leave the bottom band free for burned-in captions
    rect = [0.14, 0.40, 0.78, 0.36] if portrait else [0.07, 0.25, 0.88, 0.52]
    ax = fig.add_axes(rect)
    ax.set_facecolor(ch.background)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=20 * s, length=0, pad=10 * s)
    ax.grid(True, color="white", alpha=0.07, linewidth=1)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=4 if portrait else 7))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    return fig, ax, s, portrait


def _chart_titles(fig, title: str, subtitle: str, s: float, portrait: bool, ch: Channel, source: str | None):
    x = 0.13 if portrait else 0.07
    y = 0.84 if portrait else 0.90
    fig.text(x, y, title, color="white", fontsize=(46 if portrait else 50) * s, fontweight="bold", va="center")
    fig.text(x, y - (0.045 if portrait else 0.075), subtitle, color=ch.accent, fontsize=32 * s, va="center")
    if source:
        if portrait:
            fig.text(x, 0.345, source, color="#5b6472", fontsize=17 * s)
        else:
            fig.text(0.95, y - 0.075, source, color="#5b6472", fontsize=17 * s, ha="right", va="center")


def _save(fig, out: Path) -> Path:
    fig.savefig(out, dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def _money(x: float) -> str:
    if abs(x) >= 1e9:
        return f"${x / 1e9:.2f}B"
    if abs(x) >= 1e6:
        return f"${x / 1e6:.1f}M"
    if abs(x) >= 100:
        return f"${x:,.0f}"
    return f"${x:,.3f}" if abs(x) < 1 else f"${x:,.2f}"


def price_chart(v: dict, ch: Channel, W: int, H: int, out: Path) -> Path:
    sym, days = v["symbol"], v["days"]
    df = market.klines(sym, days)
    fig, ax, s, portrait = _chart_canvas(W, H, ch)
    first, last = df["o"].iloc[0], df["c"].iloc[-1]
    chg = (last / first - 1) * 100
    color = ch.accent
    ax.plot(df["t"], df["c"], color=color, linewidth=4 * s)
    ax.fill_between(df["t"], df["c"], df["c"].min(), color=color, alpha=0.10)
    ax.scatter([df["t"].iloc[-1]], [last], s=220 * s, color=color, zorder=5)
    span = df["c"].max() - df["c"].min()
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda y, _: f"${y:,.2f}" if span < 5 else (f"${y:,.1f}" if span < 50 else _money(y))))
    base = sym.replace("USDT", "")
    _chart_titles(fig, f"{base} price, last {days} days", f"{_money(last)}   {chg:+.2f}%", s, portrait, ch,
                  "Source: Binance USDT-M futures")
    return _save(fig, out)


def funding_chart(v: dict, ch: Channel, W: int, H: int, out: Path) -> Path:
    sym, days = v["symbol"], v["days"]
    df = market.funding(sym, days)
    fig, ax, s, portrait = _chart_canvas(W, H, ch)
    colors = [GREEN if r >= 0 else RED for r in df["rate_pct"]]
    width = max(0.08, days / max(len(df), 1) * 0.7)
    ax.bar(df["t"], df["rate_pct"], color=colors, width=width)
    ax.axhline(0, color="white", alpha=0.3, linewidth=1.5)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:.3f}%"))
    base = sym.replace("USDT", "")
    _chart_titles(fig, f"{base} funding rate, last {days} days",
                  f"Average {df['rate_pct'].mean():+.4f}% per 8h", s, portrait, ch, "Source: Binance USDT-M futures")
    return _save(fig, out)


def oi_chart(v: dict, ch: Channel, W: int, H: int, out: Path) -> Path:
    sym, days = v["symbol"], v["days"]
    df = market.open_interest(sym, days)
    fig, ax, s, portrait = _chart_canvas(W, H, ch)
    ax.plot(df["t"], df["oi_usd"], color=ch.accent, linewidth=4 * s)
    ax.fill_between(df["t"], df["oi_usd"], df["oi_usd"].min(), color=ch.accent, alpha=0.10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: _money(y)))
    chg = (df["oi_usd"].iloc[-1] / df["oi_usd"].iloc[0] - 1) * 100
    base = sym.replace("USDT", "")
    _chart_titles(fig, f"{base} open interest, last {days} days",
                  f"{_money(df['oi_usd'].iloc[-1])}   {chg:+.2f}%", s, portrait, ch, "Source: Binance USDT-M futures")
    return _save(fig, out)


def ls_chart(v: dict, ch: Channel, W: int, H: int, out: Path) -> Path:
    sym, days = v["symbol"], v["days"]
    df = market.long_short(sym, days)
    fig, ax, s, portrait = _chart_canvas(W, H, ch)
    ax.plot(df["t"], df["ratio"], color=ch.accent, linewidth=4 * s)
    ax.axhline(1.0, color="white", alpha=0.35, linewidth=1.5, linestyle="--")
    base = sym.replace("USDT", "")
    _chart_titles(fig, f"{base} long/short account ratio",
                  f"Now {df['ratio'].iloc[-1]:.2f} longs per short", s, portrait, ch, "Source: Binance USDT-M futures")
    return _save(fig, out)


def bar_chart(v: dict, ch: Channel, W: int, H: int, out: Path) -> Path:
    s = min(W, H) / 1080
    portrait = H > W
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=ch.background)
    ax = fig.add_axes([0.13, 0.40, 0.78, 0.36] if portrait else [0.08, 0.25, 0.86, 0.52])
    ax.set_facecolor(ch.background)
    for spine in ax.spines.values():
        spine.set_visible(False)
    labels, values, unit = v["labels"], v["values"], v.get("unit", "")
    bars = ax.bar(labels, values, color=ch.accent, width=0.6)
    ax.tick_params(colors=MUTED, labelsize=22 * s, length=0)
    ax.set_yticks([])
    top = max(values) if values else 1
    for b, val in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + top * 0.02, f"{val:,.4g}{unit}",
                ha="center", va="bottom", color="white", fontsize=26 * s, fontweight="bold")
    ax.set_ylim(0, top * 1.18)
    x = 0.13 if portrait else 0.08
    fig.text(x, 0.84 if portrait else 0.88, v.get("title", ""), color="white",
             fontsize=(42 if portrait else 48) * s, fontweight="bold", va="center", wrap=True)
    return _save(fig, out)


# ----------------------------------------------------------------------------- PIL cards
def _card(W: int, H: int, ch: Channel) -> tuple[Image.Image, ImageDraw.ImageDraw, float]:
    img = Image.new("RGB", (W, H), ch.background)
    d = ImageDraw.Draw(img)
    s = min(W, H) / 1080
    d.rectangle([0, 0, W, int(10 * s)], fill=ch.accent)
    d.text((int(60 * s), int(44 * s)), ch.name.upper(), font=font(int(26 * s)), fill="#5b6472")
    return img, d, s


def _center_lines(d, lines, fnt, W, y, fill, gap):
    for line in lines:
        w = fnt.getlength(line)
        d.text(((W - w) / 2, y), line, font=fnt, fill=fill)
        y += fnt.size + gap
    return y


def title_card(v: dict, ch: Channel, W: int, H: int, out: Path) -> Path:
    img, d, s = _card(W, H, ch)
    fnt = font(int(92 * s))
    lines = wrap(v.get("text", ""), fnt, int(W * 0.82))[:5]
    block = len(lines) * (fnt.size + int(20 * s))
    _center_lines(d, lines, fnt, W, (H - block) / 2, "white", int(20 * s))
    img.save(out)
    return out


def stat_card(v: dict, ch: Channel, W: int, H: int, out: Path) -> Path:
    img, d, s = _card(W, H, ch)
    big = font(int(230 * s))
    value = str(v.get("value", ""))
    while big.getlength(value) > W * 0.9 and big.size > 60:
        big = font(big.size - 10)
    label_f = font(int(54 * s), bold=False)
    label_lines = wrap(str(v.get("label", "")), label_f, int(W * 0.8))[:3]
    total = big.size + int(40 * s) + len(label_lines) * (label_f.size + int(12 * s))
    y = (H - total) / 2
    y = _center_lines(d, [value], big, W, y, ch.accent, int(40 * s))
    _center_lines(d, label_lines, label_f, W, y, "white", int(12 * s))
    img.save(out)
    return out


def timeline_card(v: dict, ch: Channel, W: int, H: int, out: Path) -> Path:
    img, d, s = _card(W, H, ch)
    events = v.get("events", [])[:6]
    year_f, text_f = font(int(54 * s)), font(int(40 * s), bold=False)
    left = int(W * 0.10)
    col = left + int(220 * s)
    rows = []
    for e in events:
        lines = wrap(str(e.get("text", "")), text_f, W - col - int(W * 0.08))[:3]
        rows.append((str(e.get("year", "")), lines))
    row_h = [max(year_f.size, len(lines) * (text_f.size + int(8 * s))) + int(44 * s) for _, lines in rows]
    y = (H - sum(row_h)) / 2
    line_x = left + int(150 * s)
    if rows:
        d.line([(line_x, y), (line_x, y + sum(row_h) - int(44 * s))], fill="#3a4250", width=max(2, int(4 * s)))
    for (year, lines), h in zip(rows, row_h):
        d.text((left - int(30 * s), y), year, font=year_f, fill=ch.accent)
        r = int(12 * s)
        d.ellipse([line_x - r, y + year_f.size / 2 - r, line_x + r, y + year_f.size / 2 + r], fill=ch.accent)
        ty = y + (year_f.size - text_f.size) / 2
        for line in lines:
            d.text((col, ty), line, font=text_f, fill="white")
            ty += text_f.size + int(8 * s)
        y += h
    img.save(out)
    return out


# ----------------------------------------------------------------------------- stock footage
def stock_clip(v: dict, W: int, H: int, cache: Path, used: set) -> Path | None:
    if not PEXELS_API_KEY:
        return None
    orientation = "portrait" if H > W else "landscape"
    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            params={"query": v.get("query", "business"), "orientation": orientation, "per_page": 15, "size": "medium"},
            headers={"Authorization": PEXELS_API_KEY}, timeout=20,
        )
        r.raise_for_status()
        videos = r.json().get("videos", [])
    except Exception as e:  # noqa: BLE001
        log.warning("Pexels search failed: %s", e)
        return None
    for vid in videos:
        if vid["id"] in used or vid.get("duration", 0) < 4:
            continue
        files = [f for f in vid.get("video_files", []) if f.get("width") and f.get("file_type") == "video/mp4"]
        good = [f for f in files if (f["width"] >= 1080 if H > W else f["width"] >= 1280)]
        if not good:
            continue
        best = min(good, key=lambda f: abs(f["width"] - W))
        path = cache / f"pexels_{vid['id']}_{best['width']}.mp4"
        if not path.exists():
            try:
                with requests.get(best["link"], stream=True, timeout=120) as dl:
                    dl.raise_for_status()
                    with open(path, "wb") as fh:
                        for chunk in dl.iter_content(1 << 20):
                            fh.write(chunk)
            except Exception as e:  # noqa: BLE001
                log.warning("Pexels download failed: %s", e)
                continue
        used.add(vid["id"])
        return path
    return None


# ----------------------------------------------------------------------------- dispatcher
RENDERERS = {
    "price_chart": price_chart, "funding_chart": funding_chart, "oi_chart": oi_chart, "ls_chart": ls_chart,
    "bar": bar_chart, "title": title_card, "stat": stat_card, "timeline": timeline_card,
}


def make_visual(v: dict, ch: Channel, W: int, H: int, out_dir: Path, tag: str, used_stock: set, fallback_text: str):
    """Return ("image" | "video", path). Never raises: falls back to a title card."""
    out_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(f"{tag}{v}".encode()).hexdigest()[:8]
    out = out_dir / f"{tag}_{key}.png"
    try:
        if v["type"] == "stock":
            clip = stock_clip(v, W, H, out_dir, used_stock)
            if clip:
                return "video", clip
            return "image", title_card({"text": fallback_text}, ch, W, H, out)
        return "image", RENDERERS[v["type"]](v, ch, W, H, out)
    except Exception as e:  # noqa: BLE001
        log.warning("Visual %s failed (%s); using title card", v.get("type"), e)
        return "image", title_card({"text": fallback_text}, ch, W, H, out)
