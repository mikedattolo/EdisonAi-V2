"""Real USPS shipping labels via EasyPost.

Shopify has no public API for a custom app to buy/print a shipping label, so Edison
buys postage through EasyPost: create a shipment (from = the shop's ship-from, to = the
order's address), buy the lowest USPS rate, download the 4x6 PNG label, print it on the
DYMO, and hand back the tracking number (written to Shopify by the caller).

EasyPost TEST keys (EZTK...) return a sample/non-postage label in the real 4x6 format —
free to demo. LIVE keys (EZAK...) buy real postage. Creating a shipment to read rates is
free in both modes; only buy() charges. The API key lives in a dedicated 0600 file because
RuntimeSettingsStore strips secrets.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger("edison.easypost")

API_BASE = "https://api.easypost.com/v2"

# Sensible default ship-from (Mike's address) so the test label works immediately.
_DEFAULT_FROM = {
    "name": "Mike Dattolo",
    "company": "TheToyBox3D",
    "street1": "58 Bald Eagle Rd",
    "street2": "",
    "city": "Hackettstown",
    "state": "NJ",
    "zip": "07840",
    "country": "US",
    "phone": "",
    "email": "mike.dattolo@yahoo.com",
}
# Default parcel for a small 3D-printed item (inches / ounces).
_DEFAULT_PARCEL = {"length": 6.0, "width": 4.0, "height": 2.0, "weight": 6.0}


class EasyPostConfigStore:
    """Persists the EasyPost key + ship-from + parcel to a 0600 JSON file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._defaults: dict[str, Any] = {
            "api_key": "",
            "from_address": dict(_DEFAULT_FROM),
            "parcel": dict(_DEFAULT_PARCEL),
            "preferred_service": "",  # "" = cheapest USPS
        }

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {k: (dict(v) if isinstance(v, dict) else v) for k, v in self._defaults.items()}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                merged = {k: (dict(v) if isinstance(v, dict) else v) for k, v in self._defaults.items()}
                for key, value in raw.items():
                    if isinstance(value, dict) and isinstance(merged.get(key), dict):
                        merged[key].update(value)
                    else:
                        merged[key] = value
                return merged
        except (OSError, json.JSONDecodeError):
            logger.warning("easypost config unreadable; using defaults")
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in self._defaults.items()}

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def full(self) -> dict[str, Any]:
        return self._read()

    @staticmethod
    def _key_mode(key: str) -> str:
        if key.startswith("EZTK"):
            return "test"
        if key.startswith("EZAK"):
            return "live"
        return "unknown" if key else "none"

    def public(self) -> dict[str, Any]:
        data = self._read()
        return {
            "has_key": bool(data.get("api_key")),
            "key_mode": self._key_mode(data.get("api_key", "")),
            "from_address": data.get("from_address", {}),
            "parcel": data.get("parcel", {}),
            "preferred_service": data.get("preferred_service", ""),
            "ready": self.is_ready(),
        }

    def is_ready(self) -> bool:
        data = self._read()
        addr = data.get("from_address") or {}
        return bool(data.get("api_key") and addr.get("street1") and addr.get("zip"))

    def update(self, *, api_key=None, from_address=None, parcel=None, preferred_service=None) -> dict[str, Any]:
        data = self._read()
        if api_key:  # empty keeps the stored key
            data["api_key"] = api_key.strip()
        if isinstance(from_address, dict):
            data["from_address"] = {**data.get("from_address", {}), **{k: v for k, v in from_address.items() if v is not None}}
        if isinstance(parcel, dict):
            merged = {**data.get("parcel", {})}
            for k, v in parcel.items():
                if v is not None:
                    try:
                        merged[k] = float(v)
                    except (TypeError, ValueError):
                        pass
            data["parcel"] = merged
        if preferred_service is not None:
            data["preferred_service"] = preferred_service.strip()
        self._write(data)
        return self.public()

    def clear_key(self) -> dict[str, Any]:
        data = self._read()
        data["api_key"] = ""
        self._write(data)
        return self.public()


def _basic_auth(api_key: str) -> str:
    return "Basic " + base64.b64encode((api_key + ":").encode()).decode()


class EasyPostClient:
    def __init__(self, api_key: str, timeout: int = 45) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def _req(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = API_BASE + path
        body = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Authorization", _basic_auth(self.api_key))
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:400]
            raise RuntimeError(f"EasyPost {error.code}: {detail}") from error

    @staticmethod
    def _download(url: str, timeout: int = 45) -> bytes:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()


def _choose_rate(rates: list[dict], preferred_service: str = "") -> dict | None:
    if not rates:
        return None
    usps = [r for r in rates if (r.get("carrier") or "").upper() == "USPS"]
    pool = usps or rates
    if preferred_service:
        match = next((r for r in pool if (r.get("service") or "").lower() == preferred_service.lower()), None)
        if match:
            return match
    return min(pool, key=lambda r: float(r.get("rate") or "99999"))


class EasyPostShipper:
    """High-level: build a shipment from a Toy Box shipping dict and buy/print the label."""

    def __init__(self, config: EasyPostConfigStore) -> None:
        self.config = config

    def _to_address(self, shipping: dict) -> dict:
        return {
            "name": shipping.get("name") or "",
            "street1": shipping.get("address1") or "",
            "street2": shipping.get("address2") or "",
            "city": shipping.get("city") or "",
            "state": shipping.get("state") or "",
            "zip": shipping.get("zip") or "",
            "country": shipping.get("country") or "US",
            "phone": shipping.get("phone") or "",
        }

    def _create_shipment(self, to_address: dict) -> dict:
        cfg = self.config.full()
        client = EasyPostClient(cfg["api_key"])
        payload = {
            "shipment": {
                "to_address": to_address,
                "from_address": cfg["from_address"],
                "parcel": cfg["parcel"],
                "options": {"label_format": "PNG"},
            }
        }
        created = client._req("POST", "/shipments", payload)
        rates = created.get("rates") or []
        if not rates:
            messages = created.get("messages") or []
            raise RuntimeError("EasyPost returned no rates" + (f": {json.dumps(messages)[:200]}" if messages else "."))
        chosen = _choose_rate(rates, cfg.get("preferred_service", ""))
        return {"client": client, "shipment_id": created["id"], "rate": chosen}

    def quote(self, shipping: dict) -> dict:
        """Get the rate without buying (free; for dry-run plans)."""
        ctx = self._create_shipment(self._to_address(shipping))
        rate = ctx["rate"] or {}
        return {
            "ok": True,
            "carrier": rate.get("carrier"),
            "service": rate.get("service"),
            "rate": rate.get("rate"),
        }

    def buy_and_render(self, shipping: dict, copies: int = 1) -> dict:
        """Buy the label (charges postage in live mode) and return the PNG + tracking."""
        ctx = self._create_shipment(self._to_address(shipping))
        client: EasyPostClient = ctx["client"]
        rate = ctx["rate"] or {}
        bought = client._req("POST", f"/shipments/{ctx['shipment_id']}/buy", {"rate": {"id": rate.get("id")}})
        label = bought.get("postage_label") or {}
        url = label.get("label_url")
        png = client._download(url) if url else None
        return {
            "ok": bool(png),
            "tracking_code": bought.get("tracking_code"),
            "carrier": rate.get("carrier"),
            "service": rate.get("service"),
            "rate": rate.get("rate"),
            "label_png": png,
            "label_url": url,
            "shipment_id": bought.get("id"),
        }


# --- module singleton so run_fulfillment (API layer) can read config without an import cycle ---
_STORE: EasyPostConfigStore | None = None


def set_config_store(store: EasyPostConfigStore) -> None:
    global _STORE
    _STORE = store


def get_config_store() -> EasyPostConfigStore | None:
    return _STORE
