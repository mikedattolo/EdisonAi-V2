"""DYMO LabelWriter printing via CUPS (lp). The LabelWriter 5XL is added to CUPS as a
queue (default name DYMO_5XL); labels are rendered to an image with Pillow and sent."""

from __future__ import annotations

import datetime
import os
import subprocess
import tempfile

DYMO_QUEUE = os.getenv("EDISON_DYMO_QUEUE", "DYMO_5XL")
DYMO_MEDIA = os.getenv("EDISON_DYMO_MEDIA", "w296h452")  # 4x6 shipping label
_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def status() -> dict:
    try:
        result = subprocess.run(["lpstat", "-p", DYMO_QUEUE], capture_output=True, text=True, timeout=8)
        available = result.returncode == 0
        detail = (result.stdout or result.stderr).strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        return {"queue": DYMO_QUEUE, "available": False, "detail": "CUPS (lpstat) is not available on the server."}
    return {"queue": DYMO_QUEUE, "available": available, "detail": detail or ("idle" if available else "not found")}


def _font(size: int):
    from PIL import ImageFont

    for path in _FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def print_label(title: str = "", lines: list[str] | None = None, copies: int = 1) -> dict:
    lines = lines or []
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return {"ok": False, "detail": "Pillow is not installed on the server."}

    width, height = 1200, 1800  # 4x6 inch at 300 DPI
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([18, 18, width - 18, height - 18], outline="black", width=6)
    y = 70
    if title:
        draw.text((55, y), title, fill="black", font=_font(92))
        y += 150
        draw.line([55, y, width - 55, y], fill="black", width=4)
        y += 28
    for line in lines[:18]:
        draw.text((55, y), line, fill="black", font=_font(58))
        y += 84

    handle = tempfile.NamedTemporaryFile(prefix="edison_label_", suffix=".png", delete=False)
    path = handle.name
    handle.close()
    image.save(path)
    try:
        result = subprocess.run(
            ["lp", "-d", DYMO_QUEUE, "-n", str(max(1, int(copies))), "-o", f"media={DYMO_MEDIA}", "-o", "fit-to-page", path],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as error:
        return {"ok": False, "detail": f"Could not run lp: {error.__class__.__name__}"}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if result.returncode != 0:
        return {"ok": False, "detail": (result.stderr or result.stdout).strip() or "lp returned an error."}
    return {"ok": True, "detail": result.stdout.strip() or "Label sent to the DYMO."}


def print_test() -> dict:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return print_label(
        "EDISON ToyBox3D",
        ["DYMO LabelWriter 5XL", "Test label — connection OK", "", now],
    )
