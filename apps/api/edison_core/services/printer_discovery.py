"""Scan the local network for 3D printers (Bambu, Klipper/Moonraker, OctoPrint)."""

from __future__ import annotations

import concurrent.futures
import socket

from edison_core.services import bambu_printer

PROBE_PORTS = [80, 5000, 7125, 8883, 990, 4409, 9999, 8080]


def local_subnet() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ".".join(ip.split(".")[:3])
    except OSError:
        return "192.168.1"


def _open_ports(ip: str, timeout: float = 0.4) -> list[int]:
    found: list[int] = []
    for port in PROBE_PORTS:
        sock = socket.socket()
        sock.settimeout(timeout)
        try:
            if sock.connect_ex((ip, port)) == 0:
                found.append(port)
        except OSError:
            pass
        finally:
            sock.close()
    return found


def _classify(ports: list[int]) -> tuple[str, str]:
    if 8883 in ports or 990 in ports or 4409 in ports:
        return "bambu", "Bambu Lab printer"
    if 7125 in ports:
        return "moonraker", "Klipper / Moonraker printer"
    if 5000 in ports:
        return "octoprint", "OctoPrint host"
    if 9999 in ports:
        # Creality K1/K1 SE: controllable over the stock :9999 LAN websocket.
        return "creality", "Creality K1 (LAN websocket)"
    return "unknown", "Device"


def discover(subnet: str | None = None, ssdp_timeout: float = 4.0) -> list[dict]:
    subnet = subnet or local_subnet()
    hosts = [f"{subnet}.{octet}" for octet in range(1, 255)]
    found: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=128) as pool:
        for ip, ports in zip(hosts, pool.map(_open_ports, hosts)):
            if not ports:
                continue
            kind, label = _classify(ports)
            if kind == "unknown":
                continue
            found.append({"ip": ip, "kind": kind, "label": label, "ports": ports})

    # Enrich Bambu printers with their serial + model from SSDP announcements so
    # the user never has to find the serial by hand. SSDP can also reveal Bambu
    # printers whose probe ports were briefly closed.
    try:
        announced = bambu_printer.discover_ssdp(ssdp_timeout)
    except OSError:
        announced = {}
    seen = {entry["ip"] for entry in found}
    for entry in found:
        info = announced.get(entry["ip"])
        if info:
            entry["serial"] = info.get("serial") or ""
            entry["model"] = bambu_printer.bambu_model_name(info.get("model"))
            entry["kind"] = "bambu"
    for ip, info in announced.items():
        if ip in seen:
            continue
        found.append({
            "ip": ip,
            "kind": "bambu",
            "label": "Bambu Lab printer",
            "ports": [],
            "serial": info.get("serial") or "",
            "model": bambu_printer.bambu_model_name(info.get("model")),
        })
    return found
