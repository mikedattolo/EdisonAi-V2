"""Bambu Lab LAN-mode adapter: live status over MQTT (and file upload over FTPS).

Local control needs the printer's IP, serial number, and LAN access code
(Settings -> Network -> LAN Only Mode on the printer)."""

from __future__ import annotations

import ftplib
import json
import os
import queue
import socket
import ssl
import struct
import threading
import time
import zipfile
import xml.etree.ElementTree as ET

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


def _safe_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_hex(value: str | None) -> str | None:
    """Return a #RRGGBB string from Bambu's RRGGBBAA tray_color, or None."""
    if not value:
        return None
    raw = value.lstrip("#")
    if len(raw) < 6:
        return None
    return "#" + raw[:6].upper()


def parse_3mf_filaments(path: str) -> list[dict]:
    """Read the filament list (index, color, type) from a Bambu-sliced .3mf.

    Bambu stores this in Metadata/slice_info.config (one <filament> per used slot)."""
    try:
        with zipfile.ZipFile(path) as archive:
            target = next((n for n in archive.namelist() if n.lower().endswith("slice_info.config")), None)
            if not target:
                return []
            data = archive.read(target)
    except (zipfile.BadZipFile, OSError, KeyError):
        return []
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []
    by_index: dict[int, dict] = {}
    for filament in root.iter("filament"):
        index = _safe_int(filament.get("id"))
        if index is None:
            continue
        by_index[index] = {
            "index": index,
            "color_hex": _normalize_hex(filament.get("color")),
            "type": filament.get("type") or "",
            "used_g": filament.get("used_g") or "",
        }
    return [by_index[key] for key in sorted(by_index)]


# Internal Bambu model codes (broadcast over SSDP) -> friendly names.
_BAMBU_MODELS = {
    "BL-P001": "X1C", "BL-P002": "X1", "C11": "P1P", "C12": "P1S", "C13": "X1E",
    "N1": "A1 mini", "N2S": "A1", "N2": "A1",
}


def bambu_model_name(code: str | None) -> str:
    return _BAMBU_MODELS.get((code or "").upper(), code or "")


def discover_ssdp(timeout: float = 4.0) -> dict[str, dict]:
    """Listen for Bambu SSDP announcements (multicast 239.255.255.250:2021).

    Returns {ip: {serial, model, name}}. Bambu printers broadcast their serial
    (USN) every few seconds, so we can fill it in automatically rather than
    asking the user to dig it out of the printer's settings."""
    results: dict[str, dict] = {}
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", 2021))
    except OSError:
        return results
    try:
        mreq = struct.pack("4sl", socket.inet_aton("239.255.255.250"), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    except OSError:
        pass
    sock.settimeout(1.0)
    end = time.monotonic() + max(timeout, 0.5)
    while time.monotonic() < end:
        try:
            data, addr = sock.recvfrom(2048)
        except socket.timeout:
            continue
        except OSError:
            break
        info: dict[str, str] = {}
        for line in data.decode(errors="replace").splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                info[key.strip().lower()] = value.strip()
        serial = info.get("usn") or ""
        if not serial:
            continue
        ip = info.get("location") or addr[0]
        results[ip] = {
            "serial": serial,
            "model": info.get("devmodel.bambu.com") or info.get("devmodel") or "",
            "name": info.get("devname.bambu.com") or info.get("devname") or "",
        }
    try:
        sock.close()
    except OSError:
        pass
    return results


def _chamber_socket(ip: str, access_code: str, timeout: float = 10.0):
    """Open + authenticate an A1/P1 chamber-camera socket (TLS, port 6000)."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    raw = socket.create_connection((ip, 6000), timeout=timeout)
    sock = context.wrap_socket(raw, server_hostname=ip)
    auth = bytearray()
    auth += struct.pack("<I", 0x40) + struct.pack("<I", 0x3000) + struct.pack("<I", 0) + struct.pack("<I", 0)
    user = b"bblp"
    auth += user + b"\x00" * (32 - len(user))
    code = access_code.encode()
    auth += code + b"\x00" * (32 - len(code))
    sock.sendall(auth)
    return sock


def _chamber_read(sock, count: int) -> bytes:
    buffer = b""
    while len(buffer) < count:
        chunk = sock.recv(count - len(buffer))
        if not chunk:
            raise ConnectionError("chamber stream closed")
        buffer += chunk
    return buffer


def chamber_image_frames(ip: str, access_code: str):
    """Yield JPEG frames from an A1/P1 series chamber camera (port 6000 protocol)."""
    sock = _chamber_socket(ip, access_code)
    try:
        while True:
            header = _chamber_read(sock, 16)
            length = struct.unpack("<I", header[0:4])[0]
            if length <= 0 or length > 12_000_000:
                break
            yield _chamber_read(sock, length)
    finally:
        try:
            sock.close()
        except OSError:
            pass


def chamber_image_snapshot(ip: str, access_code: str) -> bytes | None:
    """Grab a single JPEG frame from an A1/P1 chamber camera, or None on failure."""
    try:
        sock = _chamber_socket(ip, access_code)
    except OSError:
        return None
    try:
        header = _chamber_read(sock, 16)
        length = struct.unpack("<I", header[0:4])[0]
        if length <= 0 or length > 12_000_000:
            return None
        return _chamber_read(sock, length)
    except (OSError, ConnectionError, struct.error):
        return None
    finally:
        try:
            sock.close()
        except OSError:
            pass


class _ImplicitFTPS(ftplib.FTP_TLS):
    """Implicit-TLS FTP (port 990) with data-connection session reuse.

    Bambu printers run an FTPS server that (a) wraps the control socket in TLS
    immediately and (b) requires the data connection to resume the control
    session. Python's stock FTP_TLS does neither, so we override both."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._sock = None

    @property
    def sock(self):  # noqa: ANN201
        return self._sock

    @sock.setter
    def sock(self, value) -> None:  # noqa: ANN001
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value

    def ntransfercmd(self, cmd, rest=None):  # noqa: ANN001, ANN201
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn, server_hostname=self.host, session=self.sock.session
            )
        return conn, size


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
        ams_slots: list[dict] = []
        try:
            ams_root = report.get("ams", {}) or {}
            tray_now = str(ams_root.get("tray_now", "255"))
            for unit in ams_root.get("ams", []) or []:
                for tray in unit.get("tray", []) or []:
                    tray_color = tray.get("tray_color")
                    tray_type = tray.get("tray_type")
                    has_filament = bool(tray_type) and tray_color not in (None, "", "00000000")
                    ams_slots.append({
                        "id": _safe_int(tray.get("id")),
                        "color_hex": _normalize_hex(tray_color),
                        "color": hex_to_name(tray_color) if has_filament else None,
                        "material": tray_type or None,
                        "empty": not has_filament,
                    })
                    if str(tray.get("id")) == tray_now:
                        color_hex = tray_color
                        material = tray_type
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
            "sdcard": bool(report.get("sdcard", False)),
            "ams": ams_slots,
        }

    # --- file upload (FTPS) + print control (MQTT) ---

    def upload_file(self, local_path: str, remote_name: str | None = None, timeout: float = 60.0) -> dict:
        """Upload a sliced .3mf / .gcode to the printer over implicit FTPS (port 990)."""
        if not (self.ip and self.access_code):
            return {"ok": False, "detail": "Missing IP or access code."}
        if not os.path.exists(local_path):
            return {"ok": False, "detail": "File not found on the server."}
        remote_name = remote_name or os.path.basename(local_path)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        ftp = _ImplicitFTPS(context=context)
        ftp.timeout = timeout
        try:
            ftp.connect(host=self.ip, port=990, timeout=timeout)
            ftp.login("bblp", self.access_code)
            ftp.prot_p()
            with open(local_path, "rb") as handle:
                ftp.storbinary(f"STOR {remote_name}", handle)
        except (ftplib.error_perm,) as error:
            detail = str(error)
            if "553" in detail:
                detail = (
                    "Printer refused to store the file (553). On X1 printers this means there's no "
                    "microSD card inserted (or it's full/locked) — insert a microSD card and try again."
                )
            return {"ok": False, "detail": detail}
        except (ftplib.Error, ssl.SSLError, OSError, EOFError) as error:  # noqa: BLE001
            return {"ok": False, "detail": f"FTP upload failed: {error.__class__.__name__}: {error}"}
        finally:
            try:
                ftp.quit()
            except Exception:  # noqa: BLE001
                pass
        return {"ok": True, "remote_name": remote_name}

    def _publish(self, payload: dict, timeout: float = 8.0) -> dict:
        if not HAVE_MQTT:
            return {"ok": False, "detail": "paho-mqtt is not installed on the server."}
        if not (self.ip and self.serial and self.access_code):
            return {"ok": False, "detail": "Missing IP, serial, or access code."}
        request_topic = f"device/{self.serial}/request"
        connected = threading.Event()
        published = threading.Event()
        state = {"published": False, "rc": None}

        client = mqtt.Client()
        client.username_pw_set("bblp", self.access_code)
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)

        def on_connect(c, _u, _flags, rc, _props=None):  # noqa: ANN001
            state["rc"] = rc
            connected.set()
            if rc == 0:
                c.publish(request_topic, json.dumps(payload), qos=1)

        def on_publish(_c, _u, _mid):  # noqa: ANN001
            state["published"] = True
            published.set()

        client.on_connect = on_connect
        client.on_publish = on_publish
        try:
            client.connect(self.ip, 8883, keepalive=20)
        except Exception as error:  # noqa: BLE001
            return {"ok": False, "detail": f"Connect failed: {error}"}
        client.loop_start()
        published.wait(timeout)
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        if not connected.is_set():
            return {"ok": False, "detail": "Could not connect (check LAN mode / access code)."}
        if state["rc"] not in (0, None):
            return {"ok": False, "detail": "Printer refused the MQTT login (access code?)."}
        if not state["published"]:
            return {"ok": False, "detail": "Connected but the command was not confirmed."}
        return {"ok": True}

    def start_print(
        self,
        remote_name: str,
        plate: int = 1,
        use_ams: bool = False,
        ams_mapping: list[int] | None = None,
        bed_leveling: bool = True,
        flow_cali: bool = False,
        vibration_cali: bool = False,
        timelapse: bool = False,
    ) -> dict:
        """Start a print of a file already uploaded to the printer.

        vibration_cali defaults False: with it on, the X1 runs a multi-minute resonance
        calibration after heating (no extrusion), which looks like the print has stalled."""
        lowered = remote_name.lower()
        if lowered.endswith((".gcode", ".gco", ".g")):
            payload = {"print": {"sequence_id": "0", "command": "gcode_file", "param": f"/{remote_name}"}}
            return self._publish(payload)
        subtask = remote_name.rsplit(".", 1)[0]
        command = {
            "sequence_id": "0",
            "command": "project_file",
            "param": f"Metadata/plate_{plate}.gcode",
            "subtask_name": subtask,
            "url": f"file:///sdcard/{remote_name}",
            "bed_type": "auto",
            "timelapse": bool(timelapse),
            "bed_leveling": bool(bed_leveling),
            "flow_cali": bool(flow_cali),
            "vibration_cali": bool(vibration_cali),
            "layer_inspect": False,
            "use_ams": bool(use_ams),
            "profile_id": "0",
            "project_id": "0",
            "subtask_id": "0",
            "task_id": "0",
        }
        if use_ams and ams_mapping:
            command["ams_mapping"] = ams_mapping
        return self._publish({"print": command})

    def pause(self) -> dict:
        return self._publish({"print": {"sequence_id": "0", "command": "pause"}})

    def resume(self) -> dict:
        return self._publish({"print": {"sequence_id": "0", "command": "resume"}})

    def stop(self) -> dict:
        return self._publish({"print": {"sequence_id": "0", "command": "stop"}})

    def set_speed(self, percent: int) -> dict:
        # Bambu has 4 speed levels: 1 silent(~50%), 2 standard(100%), 3 sport(~125%), 4 ludicrous(~150%+)
        percent = int(percent)
        if percent <= 60:
            level = "1"
        elif percent <= 110:
            level = "2"
        elif percent <= 135:
            level = "3"
        else:
            level = "4"
        return self._publish({"print": {"sequence_id": "0", "command": "print_speed", "param": level}})

    def set_light(self, on: bool) -> dict:
        return self._publish(
            {
                "system": {
                    "sequence_id": "0",
                    "command": "ledctrl",
                    "led_node": "chamber_light",
                    "led_mode": "on" if on else "off",
                    "led_on_time": 500,
                    "led_off_time": 500,
                    "loop_times": 0,
                    "interval_time": 0,
                }
            }
        )

    def send_gcode(self, lines: str) -> dict:
        return self._publish({"print": {"sequence_id": "0", "command": "gcode_line", "param": lines}})

    def home(self) -> dict:
        return self.send_gcode("G28\n")

    def jog(self, axis: str, distance: float, feedrate: int = 3000) -> dict:
        axis = (axis or "").upper()
        if axis not in ("X", "Y", "Z"):
            return {"ok": False, "detail": f"Invalid axis '{axis}'."}
        rate = 600 if axis == "Z" else feedrate
        return self.send_gcode(f"G91\nG1 {axis}{distance} F{rate}\nG90\n")
