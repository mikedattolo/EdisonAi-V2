"""Shopify order ingestion for the Toy Box.

The Edison box lives behind home NAT, so we POLL the Shopify Admin API rather than
receive webhooks (a webhook would need a public URL + TLS + tunnel). Polling only
needs a custom-app Admin API access token with read_orders and outbound HTTPS.

The token is stored in a dedicated 0600 JSON file because RuntimeSettingsStore
deliberately strips any secret-looking key. Modes:
  off    - poller idle, nothing happens
  notify - poll + DRY-RUN fulfillment (plan/route only, prints nothing)
  auto   - poll + REAL fulfillment (prints the label + starts the 3D print)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from edison_core.schemas import (
    ToyBoxFulfillItem,
    ToyBoxFulfillRequest,
    ToyBoxFulfillShipping,
)

logger = logging.getLogger("edison.shopify")

API_VERSION = "2024-10"
MODES = ("off", "notify", "auto")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_domain(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.replace("https://", "").replace("http://", "").strip("/")
    return text


class ShopifyConfigStore:
    """Persists Shopify ingestion config (incl. the admin token) to a 0600 JSON file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._defaults: dict[str, Any] = {
            "store_domain": "",
            "access_token": "",
            "mode": "off",
            "interval_seconds": 120,
            "last_poll": "",
            "last_result": "",
            "processed_ids": [],
        }

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(self._defaults)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return {**self._defaults, **raw}
        except (OSError, json.JSONDecodeError):
            logger.warning("shopify config unreadable; using defaults")
        return dict(self._defaults)

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

    def public(self) -> dict[str, Any]:
        data = self._read()
        return {
            "store_domain": data.get("store_domain", ""),
            "has_token": bool(data.get("access_token")),
            "mode": data.get("mode", "off"),
            "interval_seconds": int(data.get("interval_seconds", 120)),
            "last_poll": data.get("last_poll", ""),
            "last_result": data.get("last_result", ""),
            "processed_count": len(data.get("processed_ids", [])),
        }

    def update(
        self,
        *,
        store_domain: str | None = None,
        access_token: str | None = None,
        mode: str | None = None,
        interval_seconds: int | None = None,
    ) -> dict[str, Any]:
        data = self._read()
        if store_domain is not None:
            data["store_domain"] = normalize_domain(store_domain)
        # An empty access_token means "keep the existing one" (the UI never echoes it back).
        if access_token:
            data["access_token"] = access_token.strip()
        if mode in MODES:
            data["mode"] = mode
        if interval_seconds is not None:
            data["interval_seconds"] = max(30, min(3600, int(interval_seconds)))
        self._write(data)
        return self.public()

    def clear_token(self) -> dict[str, Any]:
        data = self._read()
        data["access_token"] = ""
        data["mode"] = "off"
        self._write(data)
        return self.public()

    def mark_processed(self, order_id: str, result: str = "") -> None:
        data = self._read()
        ids = data.get("processed_ids", [])
        if order_id not in ids:
            ids.append(order_id)
        data["processed_ids"] = ids[-500:]
        if result:
            data["last_result"] = result
        self._write(data)

    def set_last_poll(self, result: str) -> None:
        data = self._read()
        data["last_poll"] = _now_iso()
        data["last_result"] = result
        self._write(data)


class ShopifyClient:
    """Minimal Shopify Admin GraphQL client (stdlib only)."""

    def __init__(self, domain: str, token: str, timeout: int = 20) -> None:
        self.domain = normalize_domain(domain)
        self.token = token
        self.timeout = timeout

    def _graphql(self, query: str, variables: dict | None = None) -> dict:
        url = f"https://{self.domain}/admin/api/{API_VERSION}/graphql.json"
        body = json.dumps({"query": query, "variables": variables or {}}).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": self.token,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))

    def shop_name(self) -> str:
        data = self._graphql("{ shop { name myshopifyDomain } }")
        shop = (data.get("data") or {}).get("shop") or {}
        return shop.get("name") or ""

    def unfulfilled_orders(self, limit: int = 20) -> list[dict]:
        query = """
        query Orders($n: Int!) {
          orders(first: $n, query: "status:open AND fulfillment_status:unfulfilled", sortKey: CREATED_AT, reverse: true) {
            nodes {
              id
              name
              createdAt
              displayFulfillmentStatus
              displayFinancialStatus
              shippingAddress { name address1 address2 city provinceCode zip countryCodeV2 }
              lineItems(first: 25) {
                nodes { title quantity variant { selectedOptions { name value } } }
              }
            }
          }
        }
        """
        data = self._graphql(query, {"n": limit})
        if data.get("errors"):
            raise RuntimeError(str(data["errors"])[:500])
        return ((data.get("data") or {}).get("orders") or {}).get("nodes") or []


def order_to_request(order: dict, dry_run: bool) -> ToyBoxFulfillRequest:
    """Map a Shopify order node into a Toy Box fulfillment request."""
    addr = order.get("shippingAddress") or {}
    items: list[ToyBoxFulfillItem] = []
    for line in ((order.get("lineItems") or {}).get("nodes") or []):
        color = None
        for opt in (((line.get("variant") or {}).get("selectedOptions")) or []):
            if str(opt.get("name", "")).strip().lower() in ("color", "colour"):
                color = opt.get("value")
        items.append(
            ToyBoxFulfillItem(
                title=line.get("title") or "item",
                color=color,
                quantity=int(line.get("quantity") or 1),
            )
        )
    shipping = ToyBoxFulfillShipping(
        name=addr.get("name") or "",
        address1=addr.get("address1") or "",
        address2=addr.get("address2") or "",
        city=addr.get("city") or "",
        state=addr.get("provinceCode") or "",
        zip=addr.get("zip") or "",
        country=addr.get("countryCodeV2") or "US",
    )
    return ToyBoxFulfillRequest(
        order_name=order.get("name") or "order",
        items=items,
        shipping=shipping,
        dry_run=dry_run,
    )


class ShopifyPoller:
    """Background loop that pulls new unfulfilled orders and runs them through fulfillment.

    `fulfill_fn(request, store)` is injected (it lives in the API layer) to avoid a
    services->api import cycle.
    """

    def __init__(self, config_store: ShopifyConfigStore, toybox_store: Any, fulfill_fn: Callable) -> None:
        self.config = config_store
        self.toybox_store = toybox_store
        self.fulfill_fn = fulfill_fn
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:  # pragma: no cover - background loop
        while True:
            interval = 120
            try:
                cfg = self.config.full()
                interval = max(30, int(cfg.get("interval_seconds", 120)))
                if cfg.get("mode", "off") != "off" and cfg.get("store_domain") and cfg.get("access_token"):
                    await asyncio.get_event_loop().run_in_executor(None, self._poll_once)
            except Exception:  # noqa: BLE001 - the poller must never die
                logger.exception("shopify poll failed")
            await asyncio.sleep(interval)

    def _poll_once(self) -> dict[str, Any]:
        cfg = self.config.full()
        mode = cfg.get("mode", "off")
        domain = cfg.get("store_domain")
        token = cfg.get("access_token")
        if mode == "off" or not domain or not token:
            return {"checked": 0, "new_orders": 0, "mode": mode, "results": [], "detail": "Polling is off or not configured."}

        try:
            orders = ShopifyClient(domain, token).unfulfilled_orders()
        except (urllib.error.URLError, RuntimeError, ValueError) as error:
            detail = f"Shopify fetch failed: {error.__class__.__name__}: {str(error)[:200]}"
            self.config.set_last_poll(detail)
            return {"checked": 0, "new_orders": 0, "mode": mode, "results": [], "detail": detail}

        processed = set(cfg.get("processed_ids", []))
        dry = mode != "auto"
        results: list[dict[str, Any]] = []
        for order in orders:
            order_id = order.get("id")
            if not order_id or order_id in processed:
                continue
            request = order_to_request(order, dry_run=dry)
            try:
                result = self.fulfill_fn(request, self.toybox_store)
                summary = getattr(result, "summary", "") or ""
            except Exception as error:  # noqa: BLE001
                summary = f"fulfill error: {error.__class__.__name__}: {error}"
            self.config.mark_processed(order_id, summary)
            results.append({"order": order.get("name") or order_id, "dry_run": dry, "summary": summary})

        detail = (
            f"Checked {len(orders)} open order(s); {len(results)} new processed ({mode})."
            if results
            else f"Checked {len(orders)} open order(s); nothing new."
        )
        self.config.set_last_poll(detail)
        return {"checked": len(orders), "new_orders": len(results), "mode": mode, "results": results, "detail": detail}

    def poll_now(self) -> dict[str, Any]:
        return self._poll_once()
