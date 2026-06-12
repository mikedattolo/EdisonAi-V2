from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from edison_core.api.dependencies import (
    get_desktop_bridge_client,
    get_integration_discovery_service,
    get_runtime_settings_store,
    get_toybox_store,
)
from edison_core.schemas import (
    DesktopBridgeStatus,
    IntegrationScanReport,
    LocalIntegrationRecord,
    RuntimeSettingsUpdate,
    ToyBoxManagerStatus,
    ToyBoxNotificationChannel,
    ToyBoxNotificationResult,
    ToyBoxNotificationSendRequest,
    ToyBoxOrderCreate,
    ToyBoxOrderRecord,
    ToyBoxPrinterRecord,
    ToyBoxPrinterProfileCreate,
    ToyBoxPrinterProfileRecord,
    ToyBoxProductMappingCreate,
    ToyBoxProductMappingRecord,
    ToyBoxProductionLane,
    ToyBoxQueueItemCreate,
    ToyBoxQueueItemRecord,
    ToyBoxQueueStatusUpdate,
    ToyBoxSetupRequest,
    ToyBoxSetupResult,
    ToyBoxShopifyWebhookResult,
    ToyBoxDiscoveredPrinter,
    ToyBoxPrinterLiveStatus,
)
from edison_core.services import printer_discovery
from edison_core.services.bambu_printer import BambuPrinter
from edison_core.services.desktop_bridge import DesktopBridgeClient
from edison_core.services.integration_discovery import IntegrationDiscoveryService
from edison_core.services.runtime_settings import RuntimeSettingsStore
from edison_core.services.toybox_store import ToyBoxNotFoundError, ToyBoxStore


router = APIRouter(prefix="/api/v1/toybox", tags=["toybox"])


@router.get("/status", response_model=ToyBoxManagerStatus)
def toybox_status(
    discovery: IntegrationDiscoveryService = Depends(get_integration_discovery_service),
    runtime_settings: RuntimeSettingsStore = Depends(get_runtime_settings_store),
    store: ToyBoxStore = Depends(get_toybox_store),
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> ToyBoxManagerStatus:
    report = discovery.snapshot()
    runtime = runtime_settings.get()
    bridge_status = bridge.status()
    lanes = _production_lanes(report)
    printers = _printer_records(report, bridge_status, store.list_printers())
    notifications = _notification_channels(report, runtime.notifications, bridge_status)
    dashboard = {
        **store.dashboard_summary(),
        "desktop_bridge": {
            "reachable": bridge_status.reachable,
            "configured_url": bridge_status.configured_url,
            "tool_count": len(bridge_status.tools),
        },
        "shopify": {
            "store_url": runtime.toybox.get("shopify_store_url") or "",
            "webhooks_enabled": bool(runtime.toybox.get("shopify_webhooks_enabled", True)),
            "webhook_secret_configured": bool(_shopify_webhook_secret()),
            "auto_queue_orders": bool(runtime.toybox.get("auto_queue_orders", True)),
        },
    }
    recommendations = [
        item for item in report.recommendations
        if item.id in {
            "install-shopify-mcp",
            "add-desktop-tools-bridge",
            "add-fusion360-cad-mcp",
            "add-printer-mcp",
            "add-dymo-label-printing",
            "add-text-notifications",
        }
    ]
    return ToyBoxManagerStatus(
        lanes=lanes,
        printers=printers,
        notification_channels=notifications,
        recommendations=recommendations,
        dashboard=dashboard,
        detail=(
            "ToyBox3D can receive signed Shopify order webhooks, map SKUs to print jobs, "
            "track local production state, and hand off printer/label actions to the desktop bridge."
        ),
    )


@router.post("/setup/defaults", response_model=ToyBoxSetupResult)
def setup_toybox_defaults(
    payload: ToyBoxSetupRequest,
    store: ToyBoxStore = Depends(get_toybox_store),
    runtime_settings: RuntimeSettingsStore = Depends(get_runtime_settings_store),
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> ToyBoxSetupResult:
    runtime_record = runtime_settings.update(
        RuntimeSettingsUpdate(
            integrations={
                "desktop_bridge_url": payload.desktop_bridge_url,
                "fusion360_enabled": True,
                "blockbench_enabled": True,
                "slicer_bridge_enabled": True,
            },
            toybox={
                "shopify_store_url": payload.shopify_store_url,
                "order_polling_enabled": bool(payload.shopify_store_url),
                "shopify_webhooks_enabled": True,
                "auto_queue_orders": True,
                "default_slicer": payload.default_slicer,
                "dymo_printer_name": payload.dymo_printer_name,
                "auto_print_labels": False,
            },
            notifications={
                "enabled": True,
                "provider": payload.notification_provider,
                "target": payload.notification_target,
                "notify_on_print_error": True,
                "notify_on_label_error": True,
                "notify_on_order_exception": True,
            },
        )
    )
    printers = [
        store.upsert_printer(
            ToyBoxPrinterProfileCreate(
                name="Main PC Desktop Bridge",
                kind="generic",
                role="desktop_bridge",
                bridge_tool_id="desktop-bridge",
                status="ready" if payload.desktop_bridge_url else "staged",
                metadata={"url": payload.desktop_bridge_url},
            )
        ),
        store.upsert_printer(
            ToyBoxPrinterProfileCreate(
                name=payload.default_slicer,
                kind=_slicer_kind(payload.default_slicer),
                role="slicer",
                bridge_tool_id=_slicer_tool_id(payload.default_slicer),
                slicer_profile="default",
                status="ready",
            )
        ),
        store.upsert_printer(
            ToyBoxPrinterProfileCreate(
                name=payload.dymo_printer_name,
                kind="dymo",
                role="label_printer",
                bridge_tool_id="dymo-labelwriter-5xl",
                status="ready",
            )
        ),
    ]
    mappings: list[ToyBoxProductMappingRecord] = []
    if payload.seed_demo_mapping:
        mappings.append(
            store.upsert_mapping(
                ToyBoxProductMappingCreate(
                    sku="TOYBOX-CUSTOM-PRINT",
                    title="ToyBox3D Custom Print",
                    slicer_profile="default",
                    default_printer_id=printers[1].id,
                    material="PLA",
                    color="assigned per order",
                    status="draft",
                    metadata={"setup_seed": True},
                )
            )
        )
    bridge_status = bridge.status()
    return ToyBoxSetupResult(
        runtime_settings=runtime_record,
        printers=printers,
        mappings=mappings,
        bridge_status=bridge_status.model_dump(),
        detail="ToyBox3D defaults were saved locally and seeded into the print-farm database.",
    )


@router.get("/desktop-bridge", response_model=DesktopBridgeStatus)
def toybox_desktop_bridge_status(
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> DesktopBridgeStatus:
    return bridge.status()


@router.get("/printers", response_model=list[ToyBoxPrinterProfileRecord])
def list_printer_profiles(
    store: ToyBoxStore = Depends(get_toybox_store),
) -> list[ToyBoxPrinterProfileRecord]:
    return store.list_printers()


@router.post("/printers", response_model=ToyBoxPrinterProfileRecord)
def upsert_printer_profile(
    payload: ToyBoxPrinterProfileCreate,
    store: ToyBoxStore = Depends(get_toybox_store),
) -> ToyBoxPrinterProfileRecord:
    return store.upsert_printer(payload)


@router.get("/mappings", response_model=list[ToyBoxProductMappingRecord])
def list_product_mappings(
    store: ToyBoxStore = Depends(get_toybox_store),
) -> list[ToyBoxProductMappingRecord]:
    return store.list_mappings()


@router.post("/mappings", response_model=ToyBoxProductMappingRecord)
def upsert_product_mapping(
    payload: ToyBoxProductMappingCreate,
    store: ToyBoxStore = Depends(get_toybox_store),
) -> ToyBoxProductMappingRecord:
    return store.upsert_mapping(payload)


@router.get("/orders", response_model=list[ToyBoxOrderRecord])
def list_orders(
    limit: int = 100,
    store: ToyBoxStore = Depends(get_toybox_store),
) -> list[ToyBoxOrderRecord]:
    return store.list_orders(limit=limit)


@router.post("/orders", response_model=ToyBoxOrderRecord)
def upsert_order(
    payload: ToyBoxOrderCreate,
    store: ToyBoxStore = Depends(get_toybox_store),
) -> ToyBoxOrderRecord:
    return store.upsert_order(payload)


@router.post("/orders/{order_id}/queue", response_model=list[ToyBoxQueueItemRecord])
def queue_order(
    order_id: str,
    store: ToyBoxStore = Depends(get_toybox_store),
) -> list[ToyBoxQueueItemRecord]:
    try:
        return store.queue_order(order_id)
    except ToyBoxNotFoundError as error:
        raise HTTPException(status_code=404, detail="Order not found") from error


@router.post("/shopify/webhooks/orders", response_model=ToyBoxShopifyWebhookResult, status_code=202)
async def receive_shopify_order_webhook(
    request: Request,
    store: ToyBoxStore = Depends(get_toybox_store),
    runtime_settings: RuntimeSettingsStore = Depends(get_runtime_settings_store),
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> ToyBoxShopifyWebhookResult:
    raw_body = await request.body()
    secret = _shopify_webhook_secret()
    if not secret:
        raise HTTPException(status_code=409, detail="EDISON_SHOPIFY_WEBHOOK_SECRET is not configured.")
    hmac_header = request.headers.get("x-shopify-hmac-sha256") or request.headers.get("X-Shopify-Hmac-Sha256")
    if not _valid_shopify_hmac(raw_body, hmac_header, secret):
        raise HTTPException(status_code=401, detail="Invalid Shopify webhook signature.")

    try:
        payload = await request.json()
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Webhook body must be JSON.") from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Webhook JSON body must be an object.")

    runtime = runtime_settings.get()
    if runtime.toybox.get("shopify_webhooks_enabled") is False:
        return ToyBoxShopifyWebhookResult(
            accepted=False,
            topic=str(request.headers.get("x-shopify-topic") or ""),
            webhook_id=str(request.headers.get("x-shopify-webhook-id") or ""),
            detail="Shopify webhooks are disabled in Edison runtime settings.",
        )

    shop_domain = str(request.headers.get("x-shopify-shop-domain") or "")
    topic = str(request.headers.get("x-shopify-topic") or "orders/create")
    order_payload = _shopify_order_payload(payload)
    order_create = _toybox_order_from_shopify(order_payload, topic, shop_domain)
    webhook_id = str(
        request.headers.get("x-shopify-webhook-id")
        or f"{topic}:{order_create.external_order_id}:{hashlib.sha256(raw_body).hexdigest()[:16]}"
    )
    is_new_event = store.record_webhook_event(
        "shopify",
        webhook_id,
        topic,
        order_create.external_order_id,
        {"shop_domain": shop_domain},
    )
    if not is_new_event:
        return ToyBoxShopifyWebhookResult(
            accepted=True,
            duplicate=True,
            topic=topic,
            webhook_id=webhook_id,
            detail="Duplicate Shopify webhook ignored.",
        )

    order = store.upsert_order(order_create)
    queue = store.queue_order(order.id) if bool(runtime.toybox.get("auto_queue_orders", True)) else []
    notification: ToyBoxNotificationResult | None = None
    if any(item.status == "blocked" for item in queue) and runtime.notifications.get("notify_on_order_exception", True):
        notification = _send_notification(
            ToyBoxNotificationSendRequest(
                title="ToyBox3D order needs mapping",
                message=f"Shopify order {order.external_order_id} has at least one SKU without a product-to-print mapping.",
                severity="warning",
            ),
            runtime_settings,
            bridge,
        )
    return ToyBoxShopifyWebhookResult(
        accepted=True,
        duplicate=False,
        topic=topic,
        webhook_id=webhook_id,
        order=store.get_order(order.id),
        queue=queue,
        notification=notification.model_dump(mode="json") if notification else None,
        detail=f"Shopify order {order.external_order_id} was accepted and {'queued' if queue else 'stored'}.",
    )


@router.get("/printers/status", response_model=list[ToyBoxPrinterRecord])
def toybox_printer_status(
    discovery: IntegrationDiscoveryService = Depends(get_integration_discovery_service),
    store: ToyBoxStore = Depends(get_toybox_store),
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> list[ToyBoxPrinterRecord]:
    return _printer_records(discovery.snapshot(), bridge.status(), store.list_printers())


@router.get("/discover", response_model=list[ToyBoxDiscoveredPrinter])
def discover_printers(store: ToyBoxStore = Depends(get_toybox_store)) -> list[ToyBoxDiscoveredPrinter]:
    known_ips = {str(p.metadata.get("ip") or "").strip() for p in store.list_printers() if p.metadata.get("ip")}
    return [
        ToyBoxDiscoveredPrinter(
            ip=item["ip"],
            kind=item["kind"],
            label=item["label"],
            ports=item["ports"],
            already_added=item["ip"] in known_ips,
        )
        for item in printer_discovery.discover()
    ]


@router.get("/printers/{printer_id}/live", response_model=ToyBoxPrinterLiveStatus)
def printer_live_status(
    printer_id: str,
    store: ToyBoxStore = Depends(get_toybox_store),
) -> ToyBoxPrinterLiveStatus:
    printer = next((item for item in store.list_printers() if item.id == printer_id), None)
    if printer is None:
        raise HTTPException(status_code=404, detail="Printer not found")
    meta = printer.metadata or {}
    ip = str(meta.get("ip") or "").strip()
    serial = str(meta.get("serial") or "").strip()
    access = str(meta.get("access_code") or "").strip()
    if printer.kind == "bambu" and ip and serial and access:
        status = BambuPrinter(ip, serial, access).get_status()
        return ToyBoxPrinterLiveStatus(
            printer_id=printer_id,
            online=bool(status.get("online")),
            state=status.get("state"),
            progress=status.get("progress"),
            nozzle_temp=status.get("nozzle_temp"),
            bed_temp=status.get("bed_temp"),
            remaining_min=status.get("remaining_min"),
            job_name=status.get("job_name"),
            loaded_color=status.get("loaded_color") or meta.get("loaded_color"),
            loaded_material=status.get("loaded_material") or meta.get("loaded_material"),
            detail=status.get("detail"),
        )
    return ToyBoxPrinterLiveStatus(
        printer_id=printer_id,
        online=False,
        loaded_color=meta.get("loaded_color"),
        loaded_material=meta.get("loaded_material"),
        detail="Live control needs a Bambu IP, serial, and access code on this printer.",
    )


@router.post("/notifications/test", response_model=ToyBoxNotificationResult)
def test_toybox_notification(
    payload: ToyBoxNotificationSendRequest,
    runtime_settings: RuntimeSettingsStore = Depends(get_runtime_settings_store),
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> ToyBoxNotificationResult:
    return _send_notification(payload, runtime_settings, bridge)


@router.get("/queue", response_model=list[ToyBoxQueueItemRecord])
def list_queue(
    limit: int = 100,
    store: ToyBoxStore = Depends(get_toybox_store),
) -> list[ToyBoxQueueItemRecord]:
    return store.list_queue(limit=limit)


@router.post("/queue", response_model=ToyBoxQueueItemRecord)
def create_queue_item(
    payload: ToyBoxQueueItemCreate,
    store: ToyBoxStore = Depends(get_toybox_store),
) -> ToyBoxQueueItemRecord:
    return store.create_queue_item(payload)


@router.post("/queue/{item_id}/status", response_model=ToyBoxQueueItemRecord)
def update_queue_status(
    item_id: str,
    payload: ToyBoxQueueStatusUpdate,
    store: ToyBoxStore = Depends(get_toybox_store),
) -> ToyBoxQueueItemRecord:
    try:
        return store.update_queue_status(item_id, payload)
    except ToyBoxNotFoundError as error:
        raise HTTPException(status_code=404, detail="Queue item not found") from error


def _production_lanes(report: IntegrationScanReport) -> list[ToyBoxProductionLane]:
    return [
        ToyBoxProductionLane(
            id="shopify-orders",
            title="Shopify Orders",
            status="staged",
            description="Receive Shopify webhooks or poll unfulfilled orders, then create production tasks.",
            connected_integrations=["install-shopify-mcp"],
            next_steps=[
                "Create a scoped Shopify custom app token outside the repo.",
                "Register order webhook endpoints or a polling MCP tool.",
            ],
        ),
        ToyBoxProductionLane(
            id="product-print-mapping",
            title="Product-to-Print Mappings",
            status=_lane_status(report, ["workstation-print-tools", "workstation-cad-tools"]),
            description="Map SKUs to CAD/STL files, slicer profiles, color/material slots, and packaging rules.",
            connected_integrations=["workstation-print-tools", "workstation-cad-tools"],
            next_steps=[
                "Import slicer profiles and SKU model paths.",
                "Add color/material constraints per product variant.",
            ],
        ),
        ToyBoxProductionLane(
            id="print-queue",
            title="Print Queue",
            status=_lane_status(report, ["workstation-print-tools", "workstation-desktop-bridge"]),
            description="Assign orders to printers, track print state, retries, camera proof, and ETA.",
            connected_integrations=["workstation-print-tools", "workstation-desktop-bridge"],
            next_steps=[
                "Add printer adapters for Bambu/Orca/Cura workflows.",
                "Connect live printer status polling and failure events.",
            ],
        ),
        ToyBoxProductionLane(
            id="printer-management",
            title="Printer Management",
            status=_lane_status(report, ["workstation-print-tools"]),
            description="Manage printer profiles, slicer paths, camera monitors, filament, and maintenance state.",
            connected_integrations=["workstation-print-tools"],
            next_steps=[
                "Register each printer with its slicer profile and camera URL.",
                "Add printer status polling through the desktop bridge.",
            ],
        ),
        ToyBoxProductionLane(
            id="shipping-labels",
            title="Shipping Labels",
            status=_lane_status(report, ["workstation-label-printer"]),
            description="Print Shopify shipping labels through the DYMO station after QA and packing.",
            connected_integrations=["workstation-label-printer"],
            next_steps=[
                "Connect Shopify shipping-label generation or label download.",
                "Send PDF/PNG labels to the DYMO print tool.",
            ],
        ),
        ToyBoxProductionLane(
            id="notifications",
            title="Text and Push Notifications",
            status="staged",
            description="Notify you when orders fail, prints pause, printers error, labels fail, or shipping needs attention.",
            connected_integrations=["workstation-notifications"],
            next_steps=[
                "Choose Twilio, Pushover, ntfy, email, or another provider.",
                "Store provider tokens in local settings or environment variables only.",
            ],
        ),
    ]


def _printer_records(
    report: IntegrationScanReport,
    bridge_status: DesktopBridgeStatus,
    profiles: list[ToyBoxPrinterProfileRecord],
) -> list[ToyBoxPrinterRecord]:
    integrations = {item.id: item for item in report.integrations}
    print_tools = integrations.get("workstation-print-tools")
    label_printer = integrations.get("workstation-label-printer")
    desktop_bridge = integrations.get("workstation-desktop-bridge")
    cad_tools = integrations.get("workstation-cad-tools")

    records: list[ToyBoxPrinterRecord] = [
        ToyBoxPrinterRecord(
            id="desktop-bridge",
            name="Main PC Desktop Tools Bridge",
            kind="generic",
            role="desktop_bridge",
            status="ready" if bridge_status.reachable else _integration_status(desktop_bridge),
            detail="Required to control Windows apps, scan allowlisted folders, run Fusion scripts, launch slicers, and print labels.",
            paths=bridge_status.allowed_roots or (desktop_bridge.paths if desktop_bridge else []),
            metadata={"configured_url": bridge_status.configured_url, "tool_count": len(bridge_status.tools)},
        ),
        ToyBoxPrinterRecord(
            id="fusion360",
            name="Fusion 360 CAD Automation",
            kind="generic",
            role="desktop_bridge",
            status=_integration_status(cad_tools),
            detail="Generate Fusion Python scripts, run them on the main PC, and export STEP/STL files back to Edison.",
            paths=cad_tools.paths if cad_tools else [],
        ),
        ToyBoxPrinterRecord(
            id="bambu-orca-cura",
            name="Bambu / Orca / Cura Slicer Toolchain",
            kind="bambu",
            role="slicer",
            status=_integration_status(print_tools),
            detail="Use installed slicers as production handoff tools until direct printer APIs are registered.",
            paths=print_tools.paths if print_tools else [],
        ),
        ToyBoxPrinterRecord(
            id="dymo-5xl",
            name="DYMO Shipping Label Station",
            kind="dymo",
            role="label_printer",
            status=_integration_status(label_printer),
            detail="Print Shopify shipping labels through the detected DYMO LabelWriter 5XL printer.",
            paths=[],
            metadata={"printer_matches": (label_printer.metadata.get("printer_matches") if label_printer else [])},
        ),
    ]
    for profile in profiles:
        records.append(
            ToyBoxPrinterRecord(
                id=profile.id,
                name=profile.name,
                kind=profile.kind,
                role=profile.role,
                status=_profile_status(profile.status),
                detail=f"Local ToyBox profile for {profile.role.replace('_', ' ')}.",
                paths=[],
                metadata={
                    **profile.metadata,
                    "bridge_tool_id": profile.bridge_tool_id,
                    "slicer_profile": profile.slicer_profile,
                    "camera_url": profile.camera_url,
                },
            )
        )
    for printer in bridge_status.three_d_printers:
        printer_id = str(printer.get("id") or printer.get("serial") or printer.get("name") or "printer")
        records.append(
            ToyBoxPrinterRecord(
                id=f"bridge-{printer_id}",
                name=str(printer.get("name") or printer_id),
                kind=_printer_kind(str(printer.get("kind") or printer.get("slicer") or "generic")),
                role="printer",
                status="ready" if printer.get("host") or printer.get("camera_url") else "staged",
                detail="3D printer registered in the desktop bridge.",
                metadata=printer,
            )
        )
    return records


def _notification_channels(
    report: IntegrationScanReport,
    notification_settings: dict[str, Any],
    bridge_status: DesktopBridgeStatus,
) -> list[ToyBoxNotificationChannel]:
    desktop_status = "ready" if bridge_status.reachable else _lane_status(report, ["workstation-desktop-bridge"])
    provider = str(notification_settings.get("provider") or "ntfy")
    target = str(notification_settings.get("target") or "")
    enabled = bool(notification_settings.get("enabled"))
    active_status = "ready" if enabled and target else "staged"
    return [
        ToyBoxNotificationChannel(
            id="sms",
            name="SMS Alerts",
            status=active_status if provider == "twilio" else "staged",
            target="sms",
            detail="Best for urgent print-farm failures or shipping exceptions.",
            setup_hint="Add Twilio or another SMS provider via local env/settings.",
            metadata={"provider": "twilio", "active": provider == "twilio"},
        ),
        ToyBoxNotificationChannel(
            id="push",
            name="Push Alerts",
            status=active_status if provider in {"ntfy", "pushover"} else "staged",
            target="push",
            detail="Good for fast mobile notifications without SMS carrier cost.",
            setup_hint="Add Pushover, ntfy, Pushbullet, or a similar provider.",
            metadata={"provider": provider if provider in {"ntfy", "pushover"} else "ntfy", "active": provider in {"ntfy", "pushover"}},
        ),
        ToyBoxNotificationChannel(
            id="email",
            name="Email Alerts",
            status=active_status if provider == "email" else "staged",
            target="email",
            detail="Useful for order summaries, daily production reports, and non-urgent exceptions.",
            setup_hint="Add SMTP settings locally, never in source control.",
            metadata={"provider": "email", "active": provider == "email"},
        ),
        ToyBoxNotificationChannel(
            id="desktop",
            name="Desktop Alerts",
            status=desktop_status if provider == "desktop" or not enabled else "staged",
            target="desktop",
            detail="Show alerts on the main PC through the desktop bridge.",
            setup_hint="Enable the PC-side bridge and allow notification commands.",
            metadata={"provider": "desktop", "active": provider == "desktop"},
        ),
    ]


def _lane_status(report: IntegrationScanReport, integration_ids: list[str]) -> str:
    integrations = {item.id: item for item in report.integrations}
    statuses = [integrations[item_id].status for item_id in integration_ids if item_id in integrations]
    if any(status == "ready" for status in statuses):
        return "ready"
    if any(status == "staged" for status in statuses):
        return "staged"
    return "missing"


def _integration_status(integration: LocalIntegrationRecord | None) -> str:
    if integration is None:
        return "missing"
    if integration.status == "ready":
        return "ready"
    if integration.status == "staged":
        return "staged"
    return "missing"


def _profile_status(status: str) -> str:
    return status if status in {"ready", "staged", "missing"} else "missing"


def _printer_kind(value: str) -> str:
    lowered = value.lower()
    if "bambu" in lowered:
        return "bambu"
    if "orca" in lowered:
        return "orca"
    if "cura" in lowered:
        return "cura"
    if "dymo" in lowered or "label" in lowered:
        return "dymo"
    return "generic"


def _slicer_kind(name: str) -> str:
    lowered = name.lower()
    if "bambu" in lowered:
        return "bambu"
    if "orca" in lowered:
        return "orca"
    if "cura" in lowered:
        return "cura"
    return "generic"


def _slicer_tool_id(name: str) -> str:
    lowered = name.lower()
    if "bambu" in lowered:
        return "bambu-studio"
    if "orca" in lowered:
        return "orcaslicer"
    if "cura" in lowered:
        return "curaengine"
    return "slicer"


def _shopify_webhook_secret() -> str:
    return os.getenv("EDISON_SHOPIFY_WEBHOOK_SECRET", "").strip()


def _valid_shopify_hmac(raw_body: bytes, header_value: str | None, secret: str) -> bool:
    if not header_value:
        return False
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, header_value.strip())


def _shopify_order_payload(payload: dict[str, Any]) -> dict[str, Any]:
    order = payload.get("order")
    return order if isinstance(order, dict) else payload


def _toybox_order_from_shopify(order: dict[str, Any], topic: str, shop_domain: str) -> ToyBoxOrderCreate:
    external_order_id = str(
        order.get("admin_graphql_api_id")
        or order.get("id")
        or order.get("order_id")
        or order.get("name")
        or ""
    ).strip()
    if not external_order_id:
        raise HTTPException(status_code=400, detail="Shopify order payload is missing an order id.")
    raw_items = order.get("line_items") or order.get("lineItems") or order.get("items") or []
    items = [_shopify_line_item(item) for item in raw_items if isinstance(item, dict)]
    if not items:
        items = [{"sku": "", "title": str(order.get("name") or external_order_id), "quantity": 1}]
    return ToyBoxOrderCreate(
        source="shopify",
        external_order_id=external_order_id,
        status="new",
        items=items,
        shipping=_shopify_shipping(order),
        metadata={
            "topic": topic,
            "shop_domain": shop_domain,
            "order_name": order.get("name"),
            "financial_status": order.get("financial_status") or order.get("displayFinancialStatus"),
            "fulfillment_status": order.get("fulfillment_status") or order.get("displayFulfillmentStatus"),
            "email": order.get("email") or order.get("contact_email"),
        },
    )


def _shopify_line_item(item: dict[str, Any]) -> dict[str, Any]:
    sku = str(
        item.get("sku")
        or item.get("variant_sku")
        or item.get("product_sku")
        or item.get("variant_id")
        or item.get("id")
        or ""
    ).strip()
    return {
        "sku": sku,
        "title": str(item.get("title") or item.get("name") or sku or "Shopify item"),
        "quantity": _positive_int(item.get("quantity") or item.get("current_quantity"), 1),
        "variant_title": item.get("variant_title"),
        "fulfillment_status": item.get("fulfillment_status"),
        "properties": item.get("properties") if isinstance(item.get("properties"), list) else [],
    }


def _shopify_shipping(order: dict[str, Any]) -> dict[str, Any]:
    shipping = order.get("shipping_address") or order.get("shippingAddress") or {}
    customer = order.get("customer") if isinstance(order.get("customer"), dict) else {}
    return {
        "address": shipping if isinstance(shipping, dict) else {},
        "customer": {
            "first_name": customer.get("first_name") or customer.get("firstName"),
            "last_name": customer.get("last_name") or customer.get("lastName"),
            "email": customer.get("email") or order.get("email"),
            "phone": customer.get("phone") or order.get("phone"),
        },
        "shipping_lines": order.get("shipping_lines") if isinstance(order.get("shipping_lines"), list) else [],
    }


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 1)


def _send_notification(
    payload: ToyBoxNotificationSendRequest,
    runtime_settings: RuntimeSettingsStore,
    bridge: DesktopBridgeClient,
) -> ToyBoxNotificationResult:
    settings = runtime_settings.get().notifications
    provider = (payload.provider or str(settings.get("provider") or "desktop")).strip().lower()
    target = (payload.target or str(settings.get("target") or "")).strip()
    if not bool(settings.get("enabled")) and not payload.force:
        return ToyBoxNotificationResult(
            ok=False,
            provider=provider,
            target=target,
            status="disabled",
            detail="Notifications are disabled in runtime settings.",
        )
    if provider == "desktop":
        result = bridge.action("notify", {"title": payload.title, "message": payload.message, "severity": payload.severity})
        return ToyBoxNotificationResult(
            ok=result.ok,
            provider=provider,
            target=target or "desktop",
            status="sent" if result.ok else "error",
            detail=result.detail,
            metadata=result.result,
        )
    if provider == "ntfy":
        if not target:
            return ToyBoxNotificationResult(ok=False, provider=provider, status="setup_required", detail="ntfy target topic or URL is required.")
        url = target if target.startswith(("http://", "https://")) else f"https://ntfy.sh/{target.lstrip('/')}"
        try:
            with httpx.Client(timeout=8.0) as client:
                response = client.post(
                    url,
                    content=payload.message.encode("utf-8"),
                    headers={"Title": payload.title, "Priority": _ntfy_priority(payload.severity)},
                )
            response.raise_for_status()
        except httpx.HTTPError as error:
            return ToyBoxNotificationResult(
                ok=False,
                provider=provider,
                target=target,
                status="error",
                detail=f"ntfy notification failed: {error.__class__.__name__}",
            )
        return ToyBoxNotificationResult(ok=True, provider=provider, target=target, status="sent", detail="ntfy notification sent.")
    return ToyBoxNotificationResult(
        ok=False,
        provider=provider,
        target=target,
        status="setup_required",
        detail=f"{provider} notifications are registered in settings but need a provider adapter and local secrets before sending.",
    )


def _ntfy_priority(severity: str) -> str:
    if severity == "error":
        return "urgent"
    if severity == "warning":
        return "high"
    return "default"
