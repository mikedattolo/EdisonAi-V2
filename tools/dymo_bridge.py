"""Edison DYMO print bridge (runs on the Windows PC).

Edison (on the Linux box) can't drive the LabelWriter 5XL (550-series, closed protocol).
This service receives Edison's rendered label PNG and prints it through the installed
Windows DYMO driver via GDI (System.Drawing.Printing), which is the only thing that
reliably rasterizes the 550-series.

History: an earlier version forwarded to DYMO Connect's Web Service (DWS). DWS returns
"true" but never feeds paper on this networked 5XL, so we switched to the Windows driver.
The driver path reports real spooler status (PagesPrinted) and physically prints.

Target = the installed Windows printer queue (default auto-picks the DYMO one; override
with EDISON_DYMO_WINDOWS_PRINTER). The 4x6 shipping label is paper "1744907 4 in x 6 in".
"""

import base64
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PRINTER_OVERRIDE = os.getenv("EDISON_DYMO_WINDOWS_PRINTER", "").strip()
PRINTER_HOST = os.getenv("EDISON_DYMO_HOST", "192.168.1.182").strip()
LISTEN_PORT = 8088
CREATE_NO_WINDOW = 0x08000000

PRINT_PS1 = os.path.join(tempfile.gettempdir(), "edison_dymo_print.ps1")

_PRINT_SCRIPT = r"""
param([Parameter(Mandatory=$true)][string]$ImagePath,
      [Parameter(Mandatory=$true)][string]$Printer,
      [int]$Copies=1)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
$img=[System.Drawing.Image]::FromFile($ImagePath)
try {
  $doc=New-Object System.Drawing.Printing.PrintDocument
  $doc.PrinterSettings.PrinterName=$Printer
  if(-not $doc.PrinterSettings.IsValid){ throw "printer not found: $Printer" }
  if($Copies -gt 1){ $doc.PrinterSettings.Copies=[int16]$Copies }
  $target=$null
  foreach($ps in $doc.PrinterSettings.PaperSizes){
    if($ps.PaperName -match '1744907' -or ($ps.Width -ge 405 -and $ps.Width -le 415 -and $ps.Height -ge 620 -and $ps.Height -le 635)){ $target=$ps; break }
  }
  if($target){ $doc.DefaultPageSettings.PaperSize=$target }
  $doc.DefaultPageSettings.Margins=New-Object System.Drawing.Printing.Margins(0,0,0,0)
  $doc.add_PrintPage({ param($s,$e)
    $e.Graphics.DrawImage($img,$e.PageBounds)
    $e.HasMorePages=$false
  })
  $doc.Print()
  if($target){ Write-Output ("OK:"+$target.PaperName) } else { Write-Output "OK:default-paper" }
} finally { $img.Dispose() }
"""


def _ps(args, timeout):
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass"] + args,
        capture_output=True, text=True, timeout=timeout, creationflags=CREATE_NO_WINDOW,
    )


def list_windows_dymo():
    try:
        proc = _ps(
            ["-Command",
             "Get-Printer | Where-Object { $_.DriverName -like '*DYMO*' -or $_.Name -like '*DYMO*' -or $_.Name -like '*label*' } | Select-Object -ExpandProperty Name"],
            timeout=20,
        )
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    except Exception:
        return []


def pick_printer():
    if PRINTER_OVERRIDE:
        return PRINTER_OVERRIDE
    printers = list_windows_dymo()
    return printers[0] if printers else "DYMO LabelWriter 5XL"


def printer_reachable():
    try:
        with socket.create_connection((PRINTER_HOST, 9100), timeout=3):
            return True
    except OSError:
        return False


def gdi_print(image_b64, copies, printer):
    raw = base64.b64decode(image_b64)
    png = os.path.join(tempfile.gettempdir(), f"edison_label_{os.getpid()}_{int(time.time())}.png")
    with open(png, "wb") as handle:
        handle.write(raw)
    try:
        proc = _ps(
            ["-File", PRINT_PS1, "-ImagePath", png, "-Printer", printer, "-Copies", str(copies)],
            timeout=90,
        )
        ok = proc.returncode == 0 and "OK:" in (proc.stdout or "")
        detail = (proc.stdout or proc.stderr or "").strip()[-400:]
        return ok, detail
    finally:
        try:
            os.remove(png)
        except OSError:
            pass


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
            printer = pick_printer()
            installed = printer in list_windows_dymo() or bool(PRINTER_OVERRIDE)
            reachable = printer_reachable()
            available = installed
            self._json(200, {
                "available": available,
                "printer": printer,
                "reachable": reachable,
                "detail": (f"Driver ready; printing to '{printer}'." + ("" if reachable else " (printer not answering on :9100 — may be asleep)"))
                if available else "No DYMO printer installed on the bridge PC.",
            })
        elif self.path.startswith("/printers"):
            self._json(200, {"printers": list_windows_dymo(), "chosen": pick_printer(), "reachable": printer_reachable()})
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
        printer = (data.get("printer") or "").strip() or pick_printer()
        try:
            ok, detail = gdi_print(image, copies, printer)
            self._json(200, {
                "ok": ok,
                "printer": printer,
                "detail": f"Printed to '{printer}' ({detail})." if ok else f"Print failed: {detail}",
            })
        except Exception as error:
            self._json(200, {"ok": False, "detail": f"bridge error: {error.__class__.__name__}: {error}"})

    def log_message(self, *args):
        return


def keepalive():
    """Open a brief TCP session to the printer to keep its network session warm."""
    while True:
        try:
            with socket.create_connection((PRINTER_HOST, 9100), timeout=3):
                pass
        except OSError:
            pass
        time.sleep(60)


if __name__ == "__main__":
    with open(PRINT_PS1, "w", encoding="utf-8") as handle:
        handle.write(_PRINT_SCRIPT)
    threading.Thread(target=keepalive, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler).serve_forever()
