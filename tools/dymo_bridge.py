"""Edison DYMO print bridge (runs on the Windows PC).

Edison (on the Linux box) can't drive the LabelWriter 5XL (550-series, closed protocol),
but DYMO Connect's local Web Service can. This tiny HTTP service listens for Edison's
print requests and forwards them to DYMO Connect (DWS), and keeps the printer awake.

It auto-selects the locally-attached, connected printer reported by DWS. DWS can list
several entries for the same device (a local USB registration plus a network/shared one);
the network/shared entry (IsLocal=False) accepts jobs but often never feeds paper, so we
prefer IsLocal=True. Set EDISON_DYMO_PRINTER to force a specific name."""

import base64
import json
import os
import re
import ssl
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DWS_BASES = ["https://127.0.0.1:41951", "http://127.0.0.1:41951"]
PRINTER_OVERRIDE = os.getenv("EDISON_DYMO_PRINTER", "").strip()  # empty = auto-pick
PAPER = "1744907 4 in x 6 in"
LISTEN_PORT = 8088

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def dws_get(path):
    for base in DWS_BASES:
        try:
            with urllib.request.urlopen(urllib.request.Request(base + path), timeout=8, context=_ctx) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            continue
    return None


def list_printers():
    """Parse DWS GetPrinters -> [{name, local, connected}]."""
    xml = dws_get("/DYMO/DLS/Printing/GetPrinters") or ""
    out = []
    for block in re.findall(r"<LabelWriterPrinter>.*?</LabelWriterPrinter>", xml, re.S):
        name = re.search(r"<Name>(.*?)</Name>", block, re.S)
        if not name:
            continue
        out.append({
            "name": name.group(1),
            "local": "<IsLocal>True</IsLocal>" in block,
            "connected": "<IsConnected>True</IsConnected>" in block,
        })
    return out


def pick_printer():
    """Prefer override (if connected), then local+connected, then any connected, then any."""
    printers = list_printers()
    if PRINTER_OVERRIDE:
        for p in printers:
            if p["name"] == PRINTER_OVERRIDE and p["connected"]:
                return PRINTER_OVERRIDE
    for p in printers:
        if p["local"] and p["connected"]:
            return p["name"]
    for p in printers:
        if p["connected"]:
            return p["name"]
    if printers:
        return printers[0]["name"]
    return PRINTER_OVERRIDE or "DYMO LabelWriter 5XL"


def dws_print(label_xml, printer_name):
    body = urllib.parse.urlencode(
        {"printerName": printer_name, "labelXml": label_xml, "labelSetXml": ""}
    ).encode()
    last = None
    for base in DWS_BASES:
        try:
            req = urllib.request.Request(
                base + "/DYMO/DLS/Printing/PrintLabel",
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=30, context=_ctx) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as error:
            last = error
            continue
    raise last or RuntimeError("DWS unreachable")


def image_label_xml(b64):
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<DieCutLabel Version="8.0" Units="twips"><PaperOrientation>Portrait</PaperOrientation>'
        f"<Id>ExtraLarge</Id><PaperName>{PAPER}</PaperName>"
        '<DrawCommands><RoundRectangle X="0" Y="0" Width="5760" Height="8640" Rx="180" Ry="180" /></DrawCommands>'
        "<ObjectInfo><ImageObject><Name>Graphic</Name>"
        '<ForeColor Alpha="255" Red="0" Green="0" Blue="0" /><BackColor Alpha="0" Red="255" Green="255" Blue="255" />'
        "<Rotation>Rotation0</Rotation><IsMirrored>False</IsMirrored><IsVariable>False</IsVariable>"
        f"<Image>{b64}</Image><ScaleMode>Uniform</ScaleMode><BorderWidth>0</BorderWidth>"
        '<BorderColor Alpha="255" Red="0" Green="0" Blue="0" />'
        "<HorizontalAlignment>Center</HorizontalAlignment><VerticalAlignment>Center</VerticalAlignment></ImageObject>"
        '<Bounds X="120" Y="120" Width="5520" Height="8400" /></ObjectInfo></DieCutLabel>'
    )


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path.startswith("/status"):
            status = dws_get("/DYMO/DLS/Printing/StatusConnected")
            available = status is not None and "true" in status.lower()
            chosen = pick_printer() if available else ""
            self._json(200, {
                "available": available,
                "printer": chosen,
                "detail": (f"DYMO Connect ready; printing to '{chosen}'." if available
                           else "DYMO Connect service not reachable"),
            })
        elif self.path.startswith("/printers"):
            self._json(200, {"printers": list_printers(), "chosen": pick_printer()})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.startswith("/print"):
            self._json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError):
            self._json(400, {"ok": False, "detail": "bad JSON"})
            return
        image = data.get("image_base64") or ""
        if not image:
            self._json(400, {"ok": False, "detail": "no image_base64 provided"})
            return
        copies = max(1, min(20, int(data.get("copies", 1))))
        printer_name = (data.get("printer") or "").strip() or pick_printer()
        try:
            result = ""
            for _ in range(copies):
                result = dws_print(image_label_xml(image), printer_name)
            ok = "true" in (result or "").lower()
            self._json(200, {
                "ok": ok,
                "printer": printer_name,
                "detail": f"Printed via DYMO Connect to '{printer_name}'." if ok else f"DWS replied: {result}",
            })
        except Exception as error:
            self._json(200, {"ok": False, "detail": f"bridge error: {error.__class__.__name__}: {error}"})

    def log_message(self, *args):
        return


def keepalive():
    while True:
        try:
            dws_get("/DYMO/DLS/Printing/GetPrinters")
        except Exception:
            pass
        time.sleep(45)


if __name__ == "__main__":
    threading.Thread(target=keepalive, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler).serve_forever()
