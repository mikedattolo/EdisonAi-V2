"""DYMO LabelWriter labels via the Windows print bridge.

The LabelWriter 5XL (550-series) can't be driven from Linux (closed protocol), so Edison
renders the label to an image and POSTs it to a small bridge running on the Windows PC,
which forwards to DYMO Connect's local Web Service (the only thing that speaks the 5XL)."""

from __future__ import annotations

import base64
import datetime
import io
import os

import httpx

DYMO_BRIDGE = os.getenv("EDISON_DYMO_BRIDGE_URL", "http://192.168.1.31:8088")
_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def status() -> dict:
    try:
        response = httpx.get(f"{DYMO_BRIDGE}/status", timeout=8.0)
        data = response.json()
        return {"queue": "windows-bridge", "available": bool(data.get("available")), "detail": data.get("detail", "")}
    except (httpx.HTTPError, ValueError):
        return {
            "queue": "windows-bridge",
            "available": False,
            "detail": f"Windows DYMO bridge not reachable at {DYMO_BRIDGE} (is the PC on + bridge running?).",
        }


def _font(size: int):
    from PIL import ImageFont

    for path in _FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render_png(title: str, lines: list[str]) -> bytes:
    from PIL import Image, ImageDraw

    width, height = 1200, 1800  # 4x6 inch @ 300 DPI
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
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def print_image_bytes(png: bytes, copies: int = 1) -> dict:
    """Send an already-rendered label image (PNG bytes) to the DYMO bridge.

    Used for real carrier labels (e.g. EasyPost) that arrive as a finished image."""
    payload = {"image_base64": base64.b64encode(png).decode(), "copies": max(1, int(copies))}
    try:
        response = httpx.post(f"{DYMO_BRIDGE}/print", json=payload, timeout=60.0)
        data = response.json()
        return {"ok": bool(data.get("ok")), "detail": data.get("detail", "")}
    except (httpx.HTTPError, ValueError):
        return {
            "ok": False,
            "detail": f"Couldn't reach the Windows DYMO bridge at {DYMO_BRIDGE} — make sure the PC is on and the bridge is running.",
        }


def print_label(title: str = "", lines: list[str] | None = None, copies: int = 1) -> dict:
    lines = lines or []
    try:
        png = _render_png(title, lines)
    except ImportError:
        return {"ok": False, "detail": "Pillow is not installed on the server."}
    return print_image_bytes(png, copies)


def print_test() -> dict:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return print_label(
        "EDISON ToyBox3D",
        ["DYMO LabelWriter 5XL", "Test label — connection OK", "", now],
    )
