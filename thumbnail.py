"""1280x720 thumbnail: scene background, dark gradient, 2-4 big words in the channel accent."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from channels import Channel
from utils import font, run, wrap

TW, TH = 1280, 720


def _background(src: str | None, ch: Channel) -> Image.Image:
    if src and Path(src).exists():
        p = Path(src)
        if p.suffix.lower() == ".mp4":
            frame = p.with_suffix(".thumb.jpg")
            run(["ffmpeg", "-y", "-ss", "1", "-i", p, "-frames:v", "1", frame])
            p = frame
        img = Image.open(p).convert("RGB")
        ratio = max(TW / img.width, TH / img.height)
        img = img.resize((int(img.width * ratio) + 1, int(img.height * ratio) + 1))
        left, top = (img.width - TW) // 2, (img.height - TH) // 2
        img = img.crop((left, top, left + TW, top + TH))
        img = ImageEnhance.Brightness(img.filter(ImageFilter.GaussianBlur(6))).enhance(0.45)
        return img
    return Image.new("RGB", (TW, TH), ch.background)


def make_thumbnail(text: str, ch: Channel, out: Path, background: str | None = None) -> Path:
    img = _background(background, ch)
    shade = Image.new("L", (TW, TH))
    sd = ImageDraw.Draw(shade)
    for x in range(TW):
        sd.line([(x, 0), (x, TH)], fill=int(220 * max(0.0, 1 - x / (TW * 0.75))))
    img = Image.composite(Image.new("RGB", (TW, TH), "black"), img, shade)

    d = ImageDraw.Draw(img)
    words = (text or "").upper().strip()
    size = 150
    while size > 70:
        fnt = font(size)
        lines = wrap(words, fnt, int(TW * 0.62))
        if len(lines) <= 3 and all(fnt.getlength(line) <= TW * 0.64 for line in lines):
            break
        size -= 8
    fnt = font(size)
    lines = wrap(words, fnt, int(TW * 0.62))[:3]
    y = (TH - len(lines) * (size + 14)) / 2
    for i, line in enumerate(lines):
        fill = ch.accent if i == 0 else "white"
        d.text((64, y), line, font=fnt, fill=fill, stroke_width=6, stroke_fill="black")
        y += size + 14
    d.rectangle([0, TH - 14, TW, TH], fill=ch.accent)
    img.save(out, "JPEG", quality=92)
    return out
