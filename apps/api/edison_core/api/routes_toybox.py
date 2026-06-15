from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from edison_core.config import load_settings
from edison_core.api.dependencies import (
    get_desktop_bridge_client,
    get_easypost_config_store,
    get_integration_discovery_service,
    get_runtime_settings_store,
    get_shopify_config_store,
    get_shopify_poller,
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
    ToyBoxRouteRequest,
    ToyBoxRouteResult,
    ToyBoxRouteCandidate,
    ToyBoxFileRecord,
    ToyBoxFilament,
    ToyBoxPrintRequest,
    ToyBoxPrintResult,
    ToyBoxControlRequest,
    ToyBoxControlResult,
    ToyBoxLabelRequest,
    ToyBoxFulfillRequest,
    ToyBoxFulfillResult,
    ToyBoxFulfillStep,
    ShopifyConfigPublic,
    ShopifyConfigUpdate,
    ShopifyPollResult,
    EasyPostConfigPublic,
    EasyPostConfigUpdate,
    EasyPostTestResult,
)
from edison_core.services import printer_discovery
from edison_core.services import bambu_printer as bambu_camera
from edison_core.services import label_printer
from edison_core.services import easypost_shipping
from edison_core.services.easypost_shipping import EasyPostShipper
from edison_core.services.bambu_printer import BambuPrinter
from edison_core.services.creality_printer import CrealityPrinter
from edison_core.services.moonraker_printer import MoonrakerPrinter
from edison_core.services.octoprint_printer import OctoPrintPrinter
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


@router.delete("/printers/{printer_id}")
def delete_printer_profile(printer_id: str, store: ToyBoxStore = Depends(get_toybox_store)) -> dict:
    store.delete_printer(printer_id)
    return {"status": "deleted", "id": printer_id}


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
            ports=item.get("ports", []),
            already_added=item["ip"] in known_ips,
            serial=item.get("serial", ""),
            model=item.get("model", ""),
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
    host = str(meta.get("host") or meta.get("ip") or "").strip()
    api_key = str(meta.get("api_key") or "").strip()

    status: dict | None = None
    if printer.kind == "bambu" and ip and serial and access:
        status = BambuPrinter(ip, serial, access).get_status(timeout=12)
    elif printer.kind == "creality" and host:
        status = CrealityPrinter(host).get_status()
    elif printer.kind == "moonraker" and host:
        status = MoonrakerPrinter(host).get_status()
    elif printer.kind == "octoprint" and host:
        status = OctoPrintPrinter(host, api_key).get_status()

    if status is None:
        return ToyBoxPrinterLiveStatus(
            printer_id=printer_id,
            online=False,
            loaded_color=meta.get("loaded_color"),
            loaded_material=meta.get("loaded_material"),
            detail=_missing_connection_detail(printer.kind, ip, serial, access, host),
        )
    # Persist detected colors so order routing knows what's loaded/available without
    # opening a live connection per route (only writes when something changed).
    if status.get("online"):
        ams_colors = sorted({slot.get("color") for slot in (status.get("ams") or []) if slot.get("color")})
        patch: dict = {"ams_colors": ams_colors}
        if status.get("loaded_color"):
            patch["loaded_color"] = status["loaded_color"]
        if status.get("loaded_material"):
            patch["loaded_material"] = status["loaded_material"]
        try:
            store.update_printer_metadata(printer_id, patch)
        except Exception:  # noqa: BLE001
            pass

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
        sdcard=bool(status.get("sdcard")),
        ams=status.get("ams") or [],
        light_on=status.get("light_on"),
        detail=status.get("detail"),
    )


def _missing_connection_detail(kind: str, ip: str, serial: str, access: str, host: str) -> str:
    if kind == "bambu":
        missing = [label for value, label in ((ip, "IP"), (serial, "serial number"), (access, "access code")) if not value]
        if missing:
            return (
                f"Bambu live control needs the {', '.join(missing)}. Open the printer's Edit panel and add it "
                "(serial auto-fills when you Scan; enable LAN Only Mode for the access code)."
            )
        return "Bambu connection details are present but incomplete."
    if kind == "moonraker":
        return "Add the printer's host/IP. Creality K1/K1 SE also needs LAN Moonraker enabled (port 7125)."
    if kind == "octoprint":
        return "Add the OctoPrint host and API key in the Edit panel."
    return "This printer type doesn't support live control yet."


# --- per-printer file library + real print send/control -------------------

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _toybox_files_root() -> Path:
    root = Path(load_settings().artifact_root) / "toybox_files"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _file_kind(filename: str) -> str:
    lowered = filename.lower()
    if lowered.endswith(".3mf"):
        return "3mf"
    if lowered.endswith((".gcode", ".gco", ".g")):
        return "gcode"
    return "other"


def _safe_filename(name: str, fallback: str) -> str:
    cleaned = _SAFE_NAME.sub("_", (name or "").strip()).strip("._")
    return cleaned or fallback


@router.get("/printers/{printer_id}/files", response_model=list[ToyBoxFileRecord])
def list_printer_files(printer_id: str, store: ToyBoxStore = Depends(get_toybox_store)) -> list[ToyBoxFileRecord]:
    return store.list_files(printer_id)


@router.post("/printers/{printer_id}/files", response_model=ToyBoxFileRecord)
async def upload_printer_file(
    printer_id: str,
    file: UploadFile = File(...),
    name: str = Form(""),
    store: ToyBoxStore = Depends(get_toybox_store),
) -> ToyBoxFileRecord:
    try:
        store.get_printer(printer_id)
    except ToyBoxNotFoundError as error:
        raise HTTPException(status_code=404, detail="Printer not found") from error

    original = file.filename or "upload.gcode"
    kind = _file_kind(original)
    if kind == "other":
        raise HTTPException(status_code=400, detail="Only .gcode and .3mf files can be sent to a printer.")

    file_id = f"tbf_{os.urandom(8).hex()}"
    safe = _safe_filename(original, f"{file_id}.{kind}")
    target_dir = _toybox_files_root() / printer_id
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_path = target_dir / f"{file_id}__{safe}"

    size = 0
    with stored_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)
    await file.close()

    display_name = (name or "").strip() or original
    return store.add_file(printer_id, display_name, safe, kind, size, str(stored_path))


@router.delete("/files/{file_id}")
def delete_printer_file(file_id: str, store: ToyBoxStore = Depends(get_toybox_store)) -> dict:
    try:
        stored_path = store.delete_file(file_id)
    except ToyBoxNotFoundError as error:
        raise HTTPException(status_code=404, detail="File not found") from error
    try:
        Path(stored_path).unlink(missing_ok=True)
    except OSError:
        pass
    return {"status": "deleted", "id": file_id}


@router.get("/files/{file_id}/filaments", response_model=list[ToyBoxFilament])
def get_file_filaments(file_id: str, store: ToyBoxStore = Depends(get_toybox_store)) -> list[ToyBoxFilament]:
    """Read the filament colors a sliced .3mf expects (for AMS color mapping)."""
    try:
        record, stored_path = store.get_file(file_id)
    except ToyBoxNotFoundError as error:
        raise HTTPException(status_code=404, detail="File not found") from error
    if record.kind != "3mf" or not Path(stored_path).exists():
        return []
    return [ToyBoxFilament(**item) for item in bambu_camera.parse_3mf_filaments(stored_path)]


@router.post("/files/{file_id}/print", response_model=ToyBoxPrintResult)
def print_printer_file(
    file_id: str,
    payload: ToyBoxPrintRequest | None = None,
    store: ToyBoxStore = Depends(get_toybox_store),
) -> ToyBoxPrintResult:
    try:
        record, stored_path = store.get_file(file_id)
        printer = store.get_printer(record.printer_id)
    except ToyBoxNotFoundError as error:
        raise HTTPException(status_code=404, detail="File or printer not found") from error
    if not Path(stored_path).exists():
        raise HTTPException(status_code=410, detail="The stored file is missing on the server.")

    options = payload or ToyBoxPrintRequest()
    result = _send_to_printer(
        printer,
        stored_path,
        record.filename,
        record.kind,
        ams_mapping=options.ams_mapping,
        plate=options.plate,
        use_ams=options.use_ams,
    )
    queue_item_id: str | None = None
    if result.get("ok"):
        queue_item = store.create_queue_item(
            ToyBoxQueueItemCreate(
                printer_id=printer.id,
                title=record.name,
                status="printing",
                gcode_path=record.filename,
                metadata={"file_id": file_id, "sent_via": printer.kind},
            )
        )
        queue_item_id = queue_item.id
    return ToyBoxPrintResult(
        ok=bool(result.get("ok")),
        printer_id=printer.id,
        file_id=file_id,
        detail=result.get("detail") or ("Sent to printer and print started." if result.get("ok") else "Send failed."),
        queue_item_id=queue_item_id,
    )


@router.post("/printers/{printer_id}/control", response_model=ToyBoxControlResult)
def control_printer(
    printer_id: str,
    payload: ToyBoxControlRequest,
    store: ToyBoxStore = Depends(get_toybox_store),
) -> ToyBoxControlResult:
    try:
        printer = store.get_printer(printer_id)
    except ToyBoxNotFoundError as error:
        raise HTTPException(status_code=404, detail="Printer not found") from error
    result = _control_printer(printer, payload.action, payload.axis, payload.distance, payload.percent)
    return ToyBoxControlResult(
        ok=bool(result.get("ok")),
        printer_id=printer_id,
        action=payload.action,
        detail=result.get("detail") or ("Done." if result.get("ok") else "Control command failed."),
    )


def _camera_source(printer: ToyBoxPrinterProfileRecord) -> tuple[list[str], str] | None:
    """Return (ffmpeg_input_opts, url) for a printer's camera, or None if it has none.

    Bambu X1-class printers expose an encrypted RTSP liveview (enable LAN Mode
    Liveview on the printer). Any other printer can set a camera_url (an MJPEG/RTSP
    stream, or a /dev/video* device for the on-box Brio)."""
    meta = printer.metadata or {}
    ip = str(meta.get("ip") or "").strip()
    access = str(meta.get("access_code") or "").strip()
    camera_url = str(meta.get("camera_url") or "").strip()
    model = str(meta.get("model") or "").lower()
    if printer.kind == "bambu" and ip and access and "x1" in model:
        return ["-rtsp_transport", "tcp"], f"rtsps://bblp:{access}@{ip}:322/streaming/live/1"
    if camera_url:
        if camera_url.startswith("/dev/"):
            return ["-f", "v4l2"], camera_url
        if camera_url.startswith(("rtsp://", "rtsps://")):
            return ["-rtsp_transport", "tcp"], camera_url
        return [], camera_url
    return None


def _is_chamber_model(model: str) -> bool:
    """A1/A1 mini/P1S use the port-6000 chamber-image protocol (not RTSP)."""
    model = (model or "").lower()
    return ("a1" in model or "p1s" in model) and "x1" not in model


def _bambu_chamber_conn(printer: ToyBoxPrinterProfileRecord) -> tuple[str, str] | None:
    meta = printer.metadata or {}
    ip = str(meta.get("ip") or "").strip()
    access = str(meta.get("access_code") or "").strip()
    if printer.kind == "bambu" and ip and access and _is_chamber_model(str(meta.get("model") or "")):
        return ip, access
    return None


def printer_has_camera(printer: ToyBoxPrinterProfileRecord) -> bool:
    return _camera_source(printer) is not None or _bambu_chamber_conn(printer) is not None


@router.get("/printers/{printer_id}/camera")
def printer_camera_stream(printer_id: str, store: ToyBoxStore = Depends(get_toybox_store)) -> StreamingResponse:
    try:
        printer = store.get_printer(printer_id)
    except ToyBoxNotFoundError as error:
        raise HTTPException(status_code=404, detail="Printer not found") from error

    chamber = _bambu_chamber_conn(printer)
    if chamber is not None:
        ip, access = chamber

        def chamber_frames():
            try:
                for jpeg in bambu_camera.chamber_image_frames(ip, access):
                    yield (
                        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                        + str(len(jpeg)).encode()
                        + b"\r\n\r\n"
                        + jpeg
                        + b"\r\n"
                    )
            except (OSError, ConnectionError):
                return

        return StreamingResponse(
            chamber_frames(),
            media_type="multipart/x-mixed-replace;boundary=frame",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    source = _camera_source(printer)
    if source is None:
        raise HTTPException(status_code=404, detail="No camera configured for this printer.")
    input_opts, url = source
    args = [
        "ffmpeg", "-nostdin", "-loglevel", "error", "-fflags", "nobuffer",
        *input_opts, "-i", url,
        "-f", "mpjpeg", "-q:v", "6", "-r", "10", "-an", "-",
    ]
    try:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail="ffmpeg is not installed on the server.") from error

    def frames():
        try:
            while True:
                chunk = process.stdout.read(16384)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                process.kill()
            except Exception:  # noqa: BLE001
                pass

    return StreamingResponse(
        frames(),
        media_type="multipart/x-mixed-replace;boundary=ffmpeg",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/printers/{printer_id}/camera/snapshot")
def printer_camera_snapshot(printer_id: str, store: ToyBoxStore = Depends(get_toybox_store)) -> Response:
    try:
        printer = store.get_printer(printer_id)
    except ToyBoxNotFoundError as error:
        raise HTTPException(status_code=404, detail="Printer not found") from error

    chamber = _bambu_chamber_conn(printer)
    if chamber is not None:
        jpeg = bambu_camera.chamber_image_snapshot(*chamber)
        if not jpeg:
            raise HTTPException(status_code=503, detail="Camera returned no image.")
        return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})

    source = _camera_source(printer)
    if source is None:
        raise HTTPException(status_code=404, detail="No camera configured for this printer.")
    input_opts, url = source
    args = ["ffmpeg", "-nostdin", "-loglevel", "error", *input_opts, "-i", url,
            "-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "-"]
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise HTTPException(status_code=503, detail="Could not capture a camera frame.") from error
    if not result.stdout:
        raise HTTPException(status_code=503, detail="Camera returned no image (is the liveview enabled?).")
    return Response(content=result.stdout, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


@router.get("/dymo/status")
def dymo_status() -> dict:
    return label_printer.status()


@router.post("/dymo/test")
def dymo_test() -> dict:
    return label_printer.print_test()


@router.post("/dymo/print")
def dymo_print(payload: ToyBoxLabelRequest) -> dict:
    return label_printer.print_label(title=payload.title, lines=payload.lines, copies=payload.copies)


def _printer_conn(printer: ToyBoxPrinterProfileRecord) -> dict:
    meta = printer.metadata or {}
    return {
        "ip": str(meta.get("ip") or "").strip(),
        "serial": str(meta.get("serial") or "").strip(),
        "access": str(meta.get("access_code") or "").strip(),
        "host": str(meta.get("host") or meta.get("ip") or "").strip(),
        "api_key": str(meta.get("api_key") or "").strip(),
    }


def _send_to_printer(
    printer: ToyBoxPrinterProfileRecord,
    local_path: str,
    filename: str,
    kind: str,
    ams_mapping: list[int] | None = None,
    plate: int = 1,
    use_ams: bool = True,
) -> dict:
    conn = _printer_conn(printer)
    if printer.kind == "bambu":
        if not (conn["ip"] and conn["serial"] and conn["access"]):
            return {"ok": False, "detail": "Bambu needs IP, serial, and access code first."}
        bambu = BambuPrinter(conn["ip"], conn["serial"], conn["access"])
        model = str((printer.metadata or {}).get("model") or "").lower()
        status = bambu.get_status(timeout=12)
        # X1 stores sent files on the microSD card; warn early if it's missing.
        if "x1" in model and status.get("online") and status.get("sdcard") is False:
            return {"ok": False, "detail": "No microSD card detected in the X1 — insert one so it can store and print the file."}
        # Only drive the AMS if the printer actually has loaded AMS slots; a single-spool
        # printer (e.g. A1 mini without AMS) must print with use_ams off or it waits forever.
        has_ams = any(not slot.get("empty") for slot in (status.get("ams") or []))
        has_mapping = bool(ams_mapping)
        uploaded = bambu.upload_file(local_path, filename)
        if not uploaded.get("ok"):
            return uploaded
        effective_use_ams = has_ams and (use_ams or has_mapping)
        started = bambu.start_print(
            filename,
            plate=plate,
            use_ams=effective_use_ams,
            ams_mapping=ams_mapping if (has_mapping and effective_use_ams) else None,
        )
        if not started.get("ok"):
            return {"ok": False, "detail": f"Uploaded, but print start failed: {started.get('detail')}"}
        return {"ok": True, "detail": f"Uploaded {filename} and started the print."}
    if printer.kind == "moonraker":
        if not conn["host"]:
            return {"ok": False, "detail": "Moonraker host/IP is required."}
        return MoonrakerPrinter(conn["host"]).upload_and_print(local_path, filename, start=True)
    if printer.kind == "octoprint":
        if not conn["host"]:
            return {"ok": False, "detail": "OctoPrint host is required."}
        return OctoPrintPrinter(conn["host"], conn["api_key"]).upload_and_print(local_path, filename, start=True)
    if printer.kind == "creality":
        if not conn["host"]:
            return {"ok": False, "detail": "K1 host/IP is required."}
        if kind != "gcode":
            return {"ok": False, "detail": "The K1 prints .gcode — slice to gcode before sending."}
        k1 = CrealityPrinter(conn["host"])
        uploaded = k1.upload_file(local_path, filename)
        if not uploaded.get("ok"):
            return uploaded
        started = k1.start_print(filename)
        if not started.get("ok"):
            return {"ok": False, "detail": f"Uploaded, but print start failed: {started.get('detail')}"}
        return {"ok": True, "detail": f"Uploaded {filename} to the K1 and started the print."}
    return {"ok": False, "detail": f"Sending isn't supported for '{printer.kind}' printers."}


def _control_printer(
    printer: ToyBoxPrinterProfileRecord,
    action: str,
    axis: str | None = None,
    distance: float | None = None,
    percent: int | None = None,
) -> dict:
    conn = _printer_conn(printer)
    if printer.kind == "bambu":
        if not (conn["ip"] and conn["serial"] and conn["access"]):
            return {"ok": False, "detail": "Bambu needs IP, serial, and access code first."}
        adapter = BambuPrinter(conn["ip"], conn["serial"], conn["access"])
    elif printer.kind == "creality":
        if not conn["host"]:
            return {"ok": False, "detail": "Creality K1 host/IP is required."}
        adapter = CrealityPrinter(conn["host"])
    elif printer.kind == "moonraker":
        if not conn["host"]:
            return {"ok": False, "detail": "Moonraker host/IP is required."}
        adapter = MoonrakerPrinter(conn["host"])
    elif printer.kind == "octoprint":
        if not conn["host"]:
            return {"ok": False, "detail": "OctoPrint host is required."}
        adapter = OctoPrintPrinter(conn["host"], conn["api_key"])
    else:
        return {"ok": False, "detail": f"Control isn't supported for '{printer.kind}' printers."}
    if action == "jog":
        if not axis or distance is None:
            return {"ok": False, "detail": "Jog needs an axis and distance."}
        return adapter.jog(axis, distance)
    if action == "speed":
        if percent is None:
            return {"ok": False, "detail": "Speed needs a percent."}
        return adapter.set_speed(percent)
    method = {
        "pause": adapter.pause,
        "resume": adapter.resume,
        "stop": adapter.stop,
        "light_on": lambda: adapter.set_light(True),
        "light_off": lambda: adapter.set_light(False),
        "home": adapter.home,
    }.get(action)
    if method is None:
        return {"ok": False, "detail": f"Unknown action '{action}'."}
    return method()


_COLOR_WORDS = {
    "red": "red", "orange": "orange", "yellow": "yellow", "gold": "yellow", "green": "green",
    "lime": "green", "blue": "blue", "navy": "blue", "cyan": "cyan", "teal": "cyan", "aqua": "cyan",
    "purple": "purple", "violet": "purple", "magenta": "pink", "pink": "pink", "white": "white",
    "black": "black", "gray": "gray", "grey": "gray", "silver": "gray", "brown": "brown",
}


def _parse_color(text: str) -> str | None:
    tokens = set("".join(ch if ch.isalnum() else " " for ch in text.lower()).split())
    for word, canon in _COLOR_WORDS.items():
        if word in tokens:
            return canon
    return None


@router.post("/route", response_model=ToyBoxRouteResult)
def route_order(payload: ToyBoxRouteRequest, store: ToyBoxStore = Depends(get_toybox_store)) -> ToyBoxRouteResult:
    product = payload.product.strip()
    color = (payload.color or "").strip().lower() or _parse_color(product)
    product_low = product.lower()
    printers = [item for item in store.list_printers() if item.kind in {"bambu", "creality", "moonraker", "octoprint"}]

    candidates: list[ToyBoxRouteCandidate] = []
    matched = None
    matched_file = None
    for printer in printers:
        meta = printer.metadata or {}
        loaded = str(meta.get("loaded_color") or "").strip().lower()
        ams_colors = [str(item).strip().lower() for item in (meta.get("ams_colors") or []) if item]
        available = {item for item in ([loaded] + ams_colors) if item}
        assigned = meta.get("assigned_files") if isinstance(meta.get("assigned_files"), dict) else {}
        file_match = None
        for key, path in (assigned or {}).items():
            keyword = str(key).strip().lower()
            if keyword and keyword in product_low and path:
                file_match = str(path)
                break
        color_ok = (not color) or (color in available)
        available_str = ", ".join(sorted(available)) or "unknown"
        if color and color_ok:
            note = f"has {color} ({available_str})"
        elif color:
            note = f"has {available_str}, needs {color}"
        else:
            note = f"loaded: {available_str}"
        candidates.append(
            ToyBoxRouteCandidate(
                printer_id=printer.id,
                printer_name=printer.name,
                loaded_color=(color if (color and color_ok) else (loaded or (sorted(available)[0] if available else None))),
                loaded_material=meta.get("loaded_material"),
                has_file=bool(file_match),
                eligible=color_ok,
                note=note,
            )
        )
        if color_ok and matched is None:
            matched = printer
            matched_file = file_match

    if matched is not None:
        reason = f"Print on {matched.name}"
        if color:
            reason += f" — it has {color} loaded"
        if matched_file:
            reason += f", file {matched_file}"
        return ToyBoxRouteResult(
            product=product,
            color=color,
            matched_printer_id=matched.id,
            matched_printer_name=matched.name,
            assigned_file=matched_file,
            reason=reason,
            candidates=candidates,
        )
    if not printers:
        reason = "No printers added yet."
    elif color:
        reason = f"No printer currently has {color} loaded. Load {color} on one, or change the order color."
    else:
        reason = "Couldn't detect a color in the product name — include a color (e.g. 'blue keychain') or set one."
    return ToyBoxRouteResult(product=product, color=color, reason=reason, candidates=candidates)


def _printer_available_colors(printer: ToyBoxPrinterProfileRecord) -> set[str]:
    meta = printer.metadata or {}
    loaded = str(meta.get("loaded_color") or "").strip().lower()
    ams = [str(item).strip().lower() for item in (meta.get("ams_colors") or []) if item]
    return {color for color in ([loaded] + ams) if color}


@router.post("/orders/fulfill", response_model=ToyBoxFulfillResult)
def fulfill_order(payload: ToyBoxFulfillRequest, store: ToyBoxStore = Depends(get_toybox_store)) -> ToyBoxFulfillResult:
    return run_fulfillment(payload, store)


def run_fulfillment(payload: ToyBoxFulfillRequest, store: ToyBoxStore) -> ToyBoxFulfillResult:
    """Orchestrate an order: route each item to a printer by color, prep the shipping label,
    and start the prints. With dry_run=True nothing is sent to a printer or the label maker.
    Reusable by both the HTTP endpoint and the Shopify poller."""
    printers = [p for p in store.list_printers() if p.kind in {"bambu", "creality", "moonraker", "octoprint"}]
    files_by_printer: dict[str, list] = {}

    steps: list[ToyBoxFulfillStep] = []
    for item in payload.items:
        color = (item.color or _parse_color(item.title) or "").strip().lower()
        title_low = item.title.lower()
        match = None
        for printer in printers:
            if not color or color in _printer_available_colors(printer):
                match = printer
                break

        resolved_record = None
        if match is not None:
            if match.id not in files_by_printer:
                files_by_printer[match.id] = store.list_files(match.id)
            printer_files = files_by_printer[match.id]
            meta = match.metadata or {}
            assigned = meta.get("assigned_files") if isinstance(meta.get("assigned_files"), dict) else {}
            assigned_name = None
            for keyword, path in (assigned or {}).items():
                if str(keyword).strip().lower() in title_low and path:
                    assigned_name = re.sub(r"[^a-z0-9]", "", str(path).lower())
                    break
            if assigned_name:
                for record in printer_files:
                    if assigned_name in (
                        re.sub(r"[^a-z0-9]", "", record.filename.lower()),
                        re.sub(r"[^a-z0-9]", "", record.name.lower()),
                    ):
                        resolved_record = record
                        break
            if resolved_record is None:
                title_norm = re.sub(r"[^a-z0-9]", "", title_low)
                for record in printer_files:
                    stem_norm = re.sub(r"[^a-z0-9]", "", record.name.lower().split(".")[0])
                    if stem_norm and title_norm and (stem_norm in title_norm or title_norm in stem_norm):
                        resolved_record = record
                        break

        resolved_file = resolved_record.filename if resolved_record else None

        if match is None:
            action, detail, eligible = "blocked", f"No printer has {color or 'a matching'} filament loaded.", False
        elif resolved_record is None:
            action = "needs file"
            detail = f"Routed to {match.name} ({color or 'any'} ok) — assign/upload a print file named for '{item.title}'."
            eligible = True
        elif payload.dry_run or not payload.start_prints:
            action = "would print"
            why = "Dry run" if payload.dry_run else "Label-only run"
            detail = f"{why}: would print '{resolved_file}' on {match.name}" + (f" in {color}" if color else "") + "."
            eligible = True
        else:
            # Real fulfillment: actually upload + start the print on the matched printer.
            try:
                file_record, stored_path = store.get_file(resolved_record.id)
                send = _send_to_printer(match, stored_path, file_record.filename, file_record.kind, use_ams=True)
            except ToyBoxNotFoundError:
                send = {"ok": False, "detail": "Matched file is no longer on the server."}
            eligible = bool(send.get("ok"))
            action = "printing" if eligible else "send failed"
            detail = send.get("detail") or (f"Sent '{resolved_file}' to {match.name}." if eligible else "Send failed.")
            if eligible:
                store.create_queue_item(
                    ToyBoxQueueItemCreate(
                        printer_id=match.id, title=item.title, status="printing",
                        gcode_path=resolved_file, metadata={"order": payload.order_name, "color": color},
                    )
                )
        steps.append(ToyBoxFulfillStep(
            title=item.title, quantity=item.quantity, color=color or None,
            printer_id=match.id if match else None, printer_name=match.name if match else None,
            eligible=eligible, file=resolved_file, action=action, detail=detail,
        ))

    ship = payload.shipping
    addr_line = ", ".join(part for part in [ship.city, ship.state, ship.zip] if part).strip()
    label_lines = [f"Order {payload.order_name}", ""]
    label_lines += [ship.name, ship.address1]
    if ship.address2:
        label_lines.append(ship.address2)
    label_lines += [addr_line, ""]
    label_lines += [f"{i.quantity}x {i.title}" for i in payload.items]
    label_lines = [line for line in label_lines if line is not None]

    ep = easypost_shipping.get_config_store()
    ep_ready = bool(ep and ep.is_ready())
    ship_dict = {
        "name": ship.name, "address1": ship.address1, "address2": ship.address2,
        "city": ship.city, "state": ship.state, "zip": ship.zip, "country": ship.country,
    }

    if payload.dry_run or not payload.print_label:
        shipping_label = {
            "would_print": True, "method": "easypost" if ep_ready else "address-label",
            "to": ship.name, "lines": label_lines, "detail": "Label planned but not printed.",
        }
        if ep_ready:
            try:
                quote = EasyPostShipper(ep).quote(ship_dict)
                shipping_label.update({
                    "carrier": quote.get("carrier"), "service": quote.get("service"), "rate": quote.get("rate"),
                    "detail": f"Would buy {quote.get('carrier')} {quote.get('service')} @ ${quote.get('rate')} and print the real label.",
                })
            except Exception as error:  # noqa: BLE001
                shipping_label["detail"] = f"EasyPost quote failed ({str(error)[:160]}); would fall back to an address label."
    elif ep_ready:
        try:
            bought = EasyPostShipper(ep).buy_and_render(ship_dict)
            if bought.get("ok") and bought.get("label_png"):
                printed = label_printer.print_image_bytes(bought["label_png"])
                shipping_label = {
                    "printed": bool(printed.get("ok")), "method": "easypost",
                    "carrier": bought.get("carrier"), "service": bought.get("service"), "rate": bought.get("rate"),
                    "tracking_code": bought.get("tracking_code"),
                    "detail": f"{bought.get('carrier')} {bought.get('service')} label — {printed.get('detail', '')}",
                }
            else:
                shipping_label = {"printed": False, "method": "easypost", "detail": "EasyPost returned no label image."}
        except Exception as error:  # noqa: BLE001
            shipping_label = {"printed": False, "method": "easypost", "detail": f"EasyPost error: {str(error)[:200]}"}
    else:
        result = label_printer.print_label(title="TheToyBox3D", lines=label_lines)
        shipping_label = {"printed": bool(result.get("ok")), "method": "address-label", "detail": result.get("detail", ""), "lines": label_lines}

    printable = sum(1 for s in steps if s.action in ("would print", "printing"))
    label_done = (not payload.dry_run) and payload.print_label
    verb = "did" if label_done else "would"
    summary = (
        f"Order {payload.order_name}: {printable}/{len(steps)} item(s) routed to a printer; "
        f"shipping label {verb} print to the DYMO for {ship.name or 'the customer'}."
        + (" (DRY RUN — nothing was actually printed.)" if payload.dry_run else "")
    )
    return ToyBoxFulfillResult(
        order_name=payload.order_name, dry_run=payload.dry_run,
        shipping_label=shipping_label, items=steps, summary=summary,
    )


# --- Shopify order ingestion (polling; box is behind NAT so no webhook needed) -------------

@router.get("/shopify", response_model=ShopifyConfigPublic)
def get_shopify_config(config=Depends(get_shopify_config_store)) -> ShopifyConfigPublic:
    return ShopifyConfigPublic(**config.public())


@router.post("/shopify", response_model=ShopifyConfigPublic)
def set_shopify_config(payload: ShopifyConfigUpdate, config=Depends(get_shopify_config_store)) -> ShopifyConfigPublic:
    return ShopifyConfigPublic(
        **config.update(
            store_domain=payload.store_domain,
            access_token=payload.access_token,
            mode=payload.mode,
            interval_seconds=payload.interval_seconds,
        )
    )


@router.post("/shopify/test")
def test_shopify_connection(config=Depends(get_shopify_config_store)) -> dict:
    from edison_core.services.shopify_orders import ShopifyClient

    cfg = config.full()
    if not cfg.get("store_domain") or not cfg.get("access_token"):
        return {"ok": False, "detail": "Set the store domain and Admin API access token first."}
    try:
        name = ShopifyClient(cfg["store_domain"], cfg["access_token"]).shop_name()
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "detail": f"Connection failed: {error.__class__.__name__}: {str(error)[:200]}"}
    return {"ok": bool(name), "detail": f"Connected to {name}." if name else "Connected, but the token may lack read_orders."}


@router.post("/shopify/poll", response_model=ShopifyPollResult)
def poll_shopify(poller=Depends(get_shopify_poller)) -> ShopifyPollResult:
    return ShopifyPollResult(**poller.poll_now())


# --- EasyPost real USPS shipping labels -----------------------------------------------------

@router.get("/easypost", response_model=EasyPostConfigPublic)
def get_easypost_config(config=Depends(get_easypost_config_store)) -> EasyPostConfigPublic:
    return EasyPostConfigPublic(**config.public())


@router.post("/easypost", response_model=EasyPostConfigPublic)
def set_easypost_config(payload: EasyPostConfigUpdate, config=Depends(get_easypost_config_store)) -> EasyPostConfigPublic:
    return EasyPostConfigPublic(
        **config.update(
            provider=payload.provider,
            api_key=payload.api_key,
            from_address=payload.from_address.model_dump() if payload.from_address else None,
            parcel=payload.parcel.model_dump() if payload.parcel else None,
            preferred_service=payload.preferred_service,
        )
    )


@router.post("/easypost/test", response_model=EasyPostTestResult)
def test_easypost(config=Depends(get_easypost_config_store)) -> EasyPostTestResult:
    """Buy a label to the shop's own address (a self-ship) and print it. With a TEST key
    this is free and produces a sample USPS label in the real 4x6 format."""
    if not config.is_ready():
        return EasyPostTestResult(ok=False, detail="Add an EasyPost API key and a ship-from address first.")
    cfg = config.full()
    from_addr = cfg.get("from_address", {})
    ship_dict = {
        "name": from_addr.get("name", "Mike Dattolo"),
        "address1": from_addr.get("street1", ""),
        "address2": from_addr.get("street2", ""),
        "city": from_addr.get("city", ""),
        "state": from_addr.get("state", ""),
        "zip": from_addr.get("zip", ""),
        "country": from_addr.get("country", "US"),
        "phone": from_addr.get("phone", ""),
    }
    try:
        bought = EasyPostShipper(config).buy_and_render(ship_dict)
    except Exception as error:  # noqa: BLE001
        return EasyPostTestResult(ok=False, detail=f"EasyPost error: {str(error)[:300]}")
    if not (bought.get("ok") and bought.get("label_png")):
        return EasyPostTestResult(ok=False, detail="EasyPost returned no label image.")
    printed = label_printer.print_image_bytes(bought["label_png"])
    return EasyPostTestResult(
        ok=bool(printed.get("ok")),
        detail=printed.get("detail", ""),
        carrier=bought.get("carrier"),
        service=bought.get("service"),
        rate=bought.get("rate"),
        tracking_code=bought.get("tracking_code"),
        label_printed=bool(printed.get("ok")),
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
