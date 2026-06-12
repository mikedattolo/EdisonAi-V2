"""Bambu Lab LAN-mode adapter: live status over MQTT (and file upload over FTPS).

Local control needs the printer's IP, serial number, and LAN access code
(Settings -> Network -> LAN Only Mode on the printer)."""

from __future__ import annotations

import json
import queue
import ssl

try:
    import paho.mqtt.client as mqtt

    HAVE_MQTT = True
except ImportError:  # pragma: no cover
    HAVE_MQTT = False

_COLOR_TABLE = {
    "red": (200, 30, 30), "orange": (230, 120, 20), "yellow": (235, 215, 40),
    "green": (40, 170, 70), "blue": (40, 90, 200), "cyan": (40, 190, 200),
    "purple": (130, 60, 180), "pink": (235, 110, 180), "white": (235, 235, 235),
    "black": (20, 20, 20), "gray": (130, 130, 130), "brown": (120, 70, 40),
}


def hex_to_name(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.lstrip("#")
    if len(raw) < 6:
        return None
    try:
        r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    except ValueError:
        return None
    best, best_dist = None, 1e9
    for name, (cr, cg, cb) in _COLOR_TABLE.items():
        dist = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if dist < best_dist:
            best, best_dist = name, dist
    return best


class BambuPrinter:
    def __init__(self, ip: str, serial: str, access_code: str) -> None:
        self.ip = ip
        self.serial = serial
        self.access_code = access_code

    def get_status(self, timeout: float = 7.0) -> dict:
        if not HAVE_MQTT:
            return {"online": False, "detail": "paho-mqtt is not installed on the server."}
        if not (self.ip and self.serial and self.access_code):
            return {"online": False, "detail": "Missing IP, serial, or access code."}

        inbox: "queue.Queue[dict]" = queue.Queue()
        report_topic = f"device/{self.serial}/report"
        request_topic = f"device/{self.serial}/request"

        client = mqtt.Client()
        client.username_pw_set("bblp", self.access_code)
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)

        def on_connect(c, _u, _flags, _rc, _props=None):  # noqa: ANN001
            c.subscribe(report_topic)
            c.publish(request_topic, json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))

        def on_message(_c, _u, msg):  # noqa: ANN001
            try:
                data = json.loads(msg.payload.decode())
            except (ValueError, UnicodeDecodeError):
                return
            if isinstance(data, dict) and isinstance(data.get("print"), dict):
                inbox.put(data["print"])

        client.on_connect = on_connect
        client.on_message = on_message
        try:
            client.connect(self.ip, 8883, keepalive=20)
        except Exception as error:  # noqa: BLE001
            return {"online": False, "detail": f"Connect failed: {error}"}
        client.loop_start()
        try:
            report = inbox.get(timeout=timeout)
        except queue.Empty:
            report = None
        finally:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:  # noqa: BLE001
                pass
        if report is None:
            return {"online": False, "detail": "Connected but no status (check serial / access code / LAN mode)."}
        return self._parse(report)

    def _parse(self, report: dict) -> dict:
        color_hex = None
        material = None
        try:
            ams_root = report.get("ams", {}) or {}
            tray_now = str(ams_root.get("tray_now", "255"))
            for unit in ams_root.get("ams", []) or []:
                for tray in unit.get("tray", []) or []:
                    if str(tray.get("id")) == tray_now:
                        color_hex = tray.get("tray_color")
                        material = tray.get("tray_type")
            if color_hex is None:
                vt = report.get("vt_tray", {}) or {}
                color_hex = vt.get("tray_color")
                material = vt.get("tray_type")
        except (AttributeError, TypeError):
            pass
        return {
            "online": True,
            "state": report.get("gcode_state"),
            "progress": report.get("mc_percent"),
            "nozzle_temp": report.get("nozzle_temper"),
            "bed_temp": report.get("bed_temper"),
            "remaining_min": report.get("mc_remaining_time"),
            "job_name": report.get("subtask_name") or report.get("gcode_file"),
            "loaded_color": hex_to_name(color_hex),
            "loaded_material": material,
        }
