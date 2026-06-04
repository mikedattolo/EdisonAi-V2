from __future__ import annotations

from fastapi import APIRouter, Depends

from edison_core.api.dependencies import get_capability_registry, get_integration_discovery_service
from edison_core.schemas import CapabilityStatus, IntegrationScanReport, MCPServerRecord, PluginIntegrationRecord
from edison_core.services.capability_registry import CapabilityRegistry
from edison_core.services.integration_discovery import IntegrationDiscoveryService


router = APIRouter(prefix="/api/v1/capabilities", tags=["capabilities"])


@router.get("", response_model=CapabilityStatus)
def capability_status(
    registry: CapabilityRegistry = Depends(get_capability_registry),
) -> CapabilityStatus:
    return registry.snapshot()


@router.get("/mcp", response_model=list[MCPServerRecord])
def mcp_servers(
    registry: CapabilityRegistry = Depends(get_capability_registry),
) -> list[MCPServerRecord]:
    return registry.snapshot().mcp_servers


@router.get("/plugins", response_model=list[PluginIntegrationRecord])
def plugin_integrations(
    registry: CapabilityRegistry = Depends(get_capability_registry),
) -> list[PluginIntegrationRecord]:
    return registry.snapshot().plugins


@router.get("/integrations", response_model=IntegrationScanReport)
def local_integrations(
    discovery: IntegrationDiscoveryService = Depends(get_integration_discovery_service),
) -> IntegrationScanReport:
    return discovery.snapshot()
