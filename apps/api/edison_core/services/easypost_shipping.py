"""Real USPS shipping labels via a postage provider (EasyPost or Shippo).

Shopify has no public API for a custom app to buy/print a shipping label, so Edison buys
postage itself: create a shipment (from = ship-from, to = order address), buy the lowest
USPS rate, download the 4x6 PNG label, print it on the DYMO, return tracking.

Two providers are supported (chosen by `provider` in config):
  - shippo   : TEST tokens (shippo_test_...) are SELF-SERVE/instant; live needs activation.
  - easypost : keys (EZTK test / EZAK live) are gated behind account approval.

Shippo is the default because its test token is friction-free. The API key lives in a 0600
file (RuntimeSettingsStore strips secrets). Creating a shipment to read rates is free; only
buying charges, so dry-run shows a real rate quote.

(Module/classes keep the historical "EasyPost" names but are provider-agnostic.)
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

logger = logging.getLogger("edison.shipping")

EASYPOST_BASE = "https://api.easypost.com/v2"
SHIPPO_BASE = "https://api.goshippo.com"
PROVIDERS = ("shippo", "easypost")


def provider_for_key(key: str, fallback: str = "shippo") -> str:
    """The API key prefix decides the provider — foolproof regardless of any stored value.
    EasyPost keys are EZTK… (test) / EZAK… (live); Shippo tokens are shippo_test_… / shippo_live_…"""
    key = key or ""
    if key.startswith(("EZTK", "EZAK")):
        return "easypost"
    if key.startswith("shippo_"):
        return "shippo"
    return fallback if fallback in PROVIDERS else "shippo"

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
_DEFAULT_PARCEL = {"length": 6.0, "width": 4.0, "height": 2.0, "weight": 6.0}  # inches / ounces


class EasyPostConfigStore:
    """Persists provider + key + ship-from + parcel to a 0600 JSON file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._defaults: dict[str, Any] = {
            "provider": "shippo",
            "api_key": "",
            "from_address": dict(_DEFAULT_FROM),
            "parcel": dict(_DEFAULT_PARCEL),
            "preferred_service": "",  # "" = cheapest USPS
        }

    def _read(self) -> dict[str, Any]:
        base = {k: (dict(v) if isinstance(v, dict) else v) for k, v in self._defaults.items()}
        if not self.path.exists():
            return base
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if isinstance(value, dict) and isinstance(base.get(key), dict):
                        base[key].update(value)
                    else:
                        base[key] = value
        except (OSError, json.JSONDecodeError):
            logger.warning("shipping config unreadable; using defaults")
        return base

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
    def _key_mode(provider: str, key: str) -> str:
        if not key:
            return "none"
        if provider == "shippo":
            if key.startswith("shippo_test_"):
                return "test"
            if key.startswith("shippo_live_"):
                return "live"
            return "unknown"
        if key.startswith("EZTK"):
            return "test"
        if key.startswith("EZAK"):
            return "live"
        return "unknown"

    def public(self) -> dict[str, Any]:
        data = self._read()
        key = data.get("api_key", "")
        provider = provider_for_key(key, data.get("provider", "shippo"))
        return {
            "provider": provider,
            "has_key": bool(key),
            "key_mode": self._key_mode(provider, key),
            "from_address": data.get("from_address", {}),
            "parcel": data.get("parcel", {}),
            "preferred_service": data.get("preferred_service", ""),
            "ready": self.is_ready(),
        }

    def is_ready(self) -> bool:
        data = self._read()
        addr = data.get("from_address") or {}
        return bool(data.get("api_key") and addr.get("street1") and addr.get("zip"))

    def update(self, *, provider=None, api_key=None, from_address=None, parcel=None, preferred_service=None) -> dict[str, Any]:
        data = self._read()
        if provider in PROVIDERS:
            data["provider"] = provider
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


def _http_json(url: str, headers: dict, payload: dict | None = None, timeout: int = 45) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, method="POST" if body is not None else "GET")
    for key, value in headers.items():
        req.add_header(key, value)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"{url.rsplit('/', 1)[-1]} {error.code}: {detail}") from error


def _download(url: str, timeout: int = 45) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


class EasyPostShipper:
    """Provider-agnostic: build a shipment from a Toy Box shipping dict, quote or buy+render."""

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

    # ---- EasyPost ----
    def _easypost_quote(self, cfg, to_addr):
        headers = {"Authorization": "Basic " + base64.b64encode((cfg["api_key"] + ":").encode()).decode()}
        payload = {"shipment": {"to_address": to_addr, "from_address": cfg["from_address"],
                                "parcel": cfg["parcel"], "options": {"label_format": "PNG"}}}
        created = _http_json(f"{EASYPOST_BASE}/shipments", headers, payload)
        rates = created.get("rates") or []
        if not rates:
            raise RuntimeError("EasyPost returned no rates (check the addresses).")
        rate = _choose_rate(rates, cfg.get("preferred_service", ""), "carrier", "service", "rate")
        return headers, created["id"], rate

    def _easypost_buy(self, cfg, to_addr):
        headers, shipment_id, rate = self._easypost_quote(cfg, to_addr)
        bought = _http_json(f"{EASYPOST_BASE}/shipments/{shipment_id}/buy", headers, {"rate": {"id": rate.get("id")}})
        label = bought.get("postage_label") or {}
        url = label.get("label_url")
        return {
            "tracking_code": bought.get("tracking_code"),
            "carrier": rate.get("carrier"), "service": rate.get("service"), "rate": rate.get("rate"),
            "label_png": _download(url) if url else None, "label_url": url,
        }

    # ---- Shippo ----
    def _shippo_parcel(self, parcel):
        return {"length": parcel.get("length", 6), "width": parcel.get("width", 4),
                "height": parcel.get("height", 2), "distance_unit": "in",
                "weight": parcel.get("weight", 6), "mass_unit": "oz"}

    def _shippo_quote(self, cfg, to_addr):
        headers = {"Authorization": f"ShippoToken {cfg['api_key']}"}
        payload = {"address_from": cfg["from_address"], "address_to": to_addr,
                   "parcels": [self._shippo_parcel(cfg["parcel"])], "async": False}
        created = _http_json(f"{SHIPPO_BASE}/shipments/", headers, payload)
        rates = created.get("rates") or []
        if not rates:
            msgs = created.get("messages") or []
            raise RuntimeError("Shippo returned no rates" + (f": {json.dumps(msgs)[:200]}" if msgs else " (check addresses)."))
        rate = _choose_rate(rates, cfg.get("preferred_service", ""), "provider", None, "amount")
        return headers, rate

    def _shippo_buy(self, cfg, to_addr):
        headers, rate = self._shippo_quote(cfg, to_addr)
        bought = _http_json(f"{SHIPPO_BASE}/transactions/", headers,
                            {"rate": rate.get("object_id"), "label_file_type": "PNG", "async": False})
        if (bought.get("status") or "").upper() != "SUCCESS":
            msgs = "; ".join(m.get("text", "") for m in (bought.get("messages") or []))
            raise RuntimeError(f"Shippo could not buy the label: {msgs or bought.get('status')}")
        url = bought.get("label_url")
        service = (rate.get("servicelevel") or {}).get("name")
        return {
            "tracking_code": bought.get("tracking_number"),
            "carrier": rate.get("provider"), "service": service, "rate": rate.get("amount"),
            "label_png": _download(url) if url else None, "label_url": url,
        }

    # ---- public ----
    def quote(self, shipping: dict) -> dict:
        cfg = self.config.full()
        to_addr = self._to_address(shipping)
        if provider_for_key(cfg.get("api_key", ""), cfg.get("provider", "shippo")) == "shippo":
            _h, rate = self._shippo_quote(cfg, to_addr)
            return {"ok": True, "carrier": rate.get("provider"),
                    "service": (rate.get("servicelevel") or {}).get("name"), "rate": rate.get("amount")}
        _h, _id, rate = self._easypost_quote(cfg, to_addr)
        return {"ok": True, "carrier": rate.get("carrier"), "service": rate.get("service"), "rate": rate.get("rate")}

    def buy_and_render(self, shipping: dict) -> dict:
        cfg = self.config.full()
        to_addr = self._to_address(shipping)
        provider = provider_for_key(cfg.get("api_key", ""), cfg.get("provider", "shippo"))
        result = self._shippo_buy(cfg, to_addr) if provider == "shippo" else self._easypost_buy(cfg, to_addr)
        result["ok"] = bool(result.get("label_png"))
        return result


def _choose_rate(rates: list[dict], preferred: str, carrier_key: str, service_key: str | None, amount_key: str) -> dict:
    def is_usps(r: dict) -> bool:
        return (r.get(carrier_key) or "").upper() == "USPS"

    def service_of(r: dict) -> str:
        if service_key:
            return r.get(service_key) or ""
        return ((r.get("servicelevel") or {}).get("token") or (r.get("servicelevel") or {}).get("name") or "")

    pool = [r for r in rates if is_usps(r)] or rates
    if preferred:
        match = next((r for r in pool if service_of(r).lower() == preferred.lower()), None)
        if match:
            return match
    return min(pool, key=lambda r: float(r.get(amount_key) or "99999"))


_STORE: EasyPostConfigStore | None = None


def set_config_store(store: EasyPostConfigStore) -> None:
    global _STORE
    _STORE = store


def get_config_store() -> EasyPostConfigStore | None:
    return _STORE
