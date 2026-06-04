from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from edison_core.config import EdisonSettings
from edison_core.schemas import RuntimeSettingsRecord, RuntimeSettingsUpdate, utc_now


class RuntimeSettingsStore:
    sections = ("media", "integrations", "toybox", "notifications", "gallery", "hardware")
    secret_markers = ("password", "secret", "token", "api_key", "apikey", "private_key")

    def __init__(self, settings: EdisonSettings) -> None:
        self.path = settings.runtime_settings_path
        self.defaults = {
            "media": {
                "preferred_image_mode": "image",
                "default_width": 1024,
                "default_height": 1024,
                "show_outputs_in_chat": True,
            },
            "integrations": {
                "desktop_bridge_url": "",
                "fusion360_enabled": True,
                "blockbench_enabled": True,
                "slicer_bridge_enabled": True,
            },
            "toybox": {
                "shopify_store_url": "",
                "order_polling_enabled": False,
                "default_slicer": "Bambu Studio",
                "dymo_printer_name": "Mike's shipping label printer",
                "auto_print_labels": False,
            },
            "notifications": {
                "enabled": False,
                "provider": "ntfy",
                "target": "",
                "notify_on_print_error": True,
                "notify_on_label_error": True,
                "notify_on_order_exception": True,
            },
            "gallery": {
                "default_filter": "all",
                "show_documents": True,
                "show_code_specs": True,
            },
            "hardware": {
                "hailo_driver_action": "mok_enrollment_required",
                "allow_reboot_when_confirmed": False,
            },
        }

    def get(self) -> RuntimeSettingsRecord:
        payload = self._read()
        return self._record(payload)

    def update(self, update: RuntimeSettingsUpdate) -> RuntimeSettingsRecord:
        current = self._read()
        incoming = update.model_dump(exclude_none=True)
        for section in self.sections:
            if section in incoming and isinstance(incoming[section], dict):
                current[section] = {
                    **current.get(section, {}),
                    **self._sanitize_section(incoming[section]),
                }
        current["updated_at"] = utc_now().isoformat()
        self._write(current)
        return self._record(current)

    def _record(self, payload: dict[str, Any]) -> RuntimeSettingsRecord:
        merged = {section: {**self.defaults[section], **payload.get(section, {})} for section in self.sections}
        updated_at = payload.get("updated_at")
        if isinstance(updated_at, str):
            try:
                updated_at = datetime.fromisoformat(updated_at)
            except ValueError:
                updated_at = utc_now()
        if not isinstance(updated_at, datetime):
            updated_at = utc_now()
        return RuntimeSettingsRecord(
            updated_at=updated_at,
            media=merged["media"],
            integrations=merged["integrations"],
            toybox=merged["toybox"],
            notifications=merged["notifications"],
            gallery=merged["gallery"],
            hardware=merged["hardware"],
        )

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {section: dict(values) for section, values in self.defaults.items()}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {section: dict(values) for section, values in self.defaults.items()}
        if not isinstance(raw, dict):
            return {section: dict(values) for section, values in self.defaults.items()}
        return {
            section: self._sanitize_section(raw.get(section, {}))
            for section in self.sections
        } | {"updated_at": raw.get("updated_at")}

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
        tmp_path.replace(self.path)

    def _sanitize_section(self, section: Any) -> dict[str, Any]:
        if not isinstance(section, dict):
            return {}
        clean: dict[str, Any] = {}
        for key, value in section.items():
            key_text = str(key)
            if any(marker in key_text.lower() for marker in self.secret_markers):
                clean[key_text] = bool(value)
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                clean[key_text] = value
            elif isinstance(value, list):
                clean[key_text] = [item for item in value if isinstance(item, (str, int, float, bool))]
            elif isinstance(value, dict):
                clean[key_text] = {
                    str(child_key): child_value
                    for child_key, child_value in value.items()
                    if isinstance(child_value, (str, int, float, bool)) and not any(
                        marker in str(child_key).lower() for marker in self.secret_markers
                    )
                }
        return clean
