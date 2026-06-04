from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

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
)
from edison_core.services.desktop_bridge import DesktopBridgeClient
from edison_core.services.integration_discovery import IntegrationDiscoveryService
from edison_core.services.runtime_settings import RuntimeSettingsStore
from edison_core.services.toybox_store import ToyBoxNotFoundError, ToyBoxStore


router = APIRouter(prefix="/api/v1/toybox", tags=["toybox"])


@router.get("/status", response_model=ToyBoxManagerStatus)
def toybox_status(
    discovery: IntegrationDiscoveryService = Depends(get_integration_discovery_service),
) -> ToyBoxManagerStatus:
    report = discovery.snapshot()
    lanes = _production_lanes(report)
    printers = _printer_records(report)
    notifications = _notification_channels(report)
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
        detail=(
            "ToyBox3D is staged for Shopify order intake, product-to-print mapping, "
            "slicer/printer handoff, DYMO labels, and notifications."
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
                "Persist queue state and production events.",
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


def _printer_records(report: IntegrationScanReport) -> list[ToyBoxPrinterRecord]:
    integrations = {item.id: item for item in report.integrations}
    print_tools = integrations.get("workstation-print-tools")
    label_printer = integrations.get("workstation-label-printer")
    desktop_bridge = integrations.get("workstation-desktop-bridge")
    cad_tools = integrations.get("workstation-cad-tools")

    records = [
        ToyBoxPrinterRecord(
            id="desktop-bridge",
            name="Main PC Desktop Tools Bridge",
            kind="generic",
            role="desktop_bridge",
            status=_integration_status(desktop_bridge),
            detail="Required to control Windows apps, scan allowlisted folders, run Fusion scripts, launch slicers, and print labels.",
            paths=desktop_bridge.paths if desktop_bridge else [],
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
    return records


def _notification_channels(report: IntegrationScanReport) -> list[ToyBoxNotificationChannel]:
    desktop_status = _lane_status(report, ["workstation-desktop-bridge"])
    return [
        ToyBoxNotificationChannel(
            id="sms",
            name="SMS Alerts",
            status="staged",
            target="sms",
            detail="Best for urgent print-farm failures or shipping exceptions.",
            setup_hint="Add Twilio or another SMS provider via local env/settings.",
        ),
        ToyBoxNotificationChannel(
            id="push",
            name="Push Alerts",
            status="staged",
            target="push",
            detail="Good for fast mobile notifications without SMS carrier cost.",
            setup_hint="Add Pushover, ntfy, Pushbullet, or a similar provider.",
        ),
        ToyBoxNotificationChannel(
            id="email",
            name="Email Alerts",
            status="staged",
            target="email",
            detail="Useful for order summaries, daily production reports, and non-urgent exceptions.",
            setup_hint="Add SMTP settings locally, never in source control.",
        ),
        ToyBoxNotificationChannel(
            id="desktop",
            name="Desktop Alerts",
            status=desktop_status,
            target="desktop",
            detail="Show alerts on the main PC through the desktop bridge.",
            setup_hint="Enable the PC-side bridge and allow notification commands.",
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
