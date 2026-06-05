from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from uuid import uuid4

from edison_core.database import SQLiteDatabase
from edison_core.schemas import (
    ToyBoxOrderCreate,
    ToyBoxOrderRecord,
    ToyBoxPrinterProfileCreate,
    ToyBoxPrinterProfileRecord,
    ToyBoxProductMappingCreate,
    ToyBoxProductMappingRecord,
    ToyBoxQueueItemCreate,
    ToyBoxQueueItemRecord,
    ToyBoxQueueStatusUpdate,
    utc_now,
)


class ToyBoxNotFoundError(KeyError):
    pass


class ToyBoxStore:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def initialize(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS toybox_printers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    role TEXT NOT NULL,
                    bridge_tool_id TEXT,
                    slicer_profile TEXT,
                    camera_url TEXT,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_toybox_printers_name_role
                    ON toybox_printers(name, role);

                CREATE TABLE IF NOT EXISTS toybox_product_mappings (
                    id TEXT PRIMARY KEY,
                    sku TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    model_path TEXT NOT NULL DEFAULT '',
                    slicer_profile TEXT NOT NULL DEFAULT '',
                    default_printer_id TEXT,
                    material TEXT NOT NULL DEFAULT '',
                    color TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS toybox_orders (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    external_order_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    items_json TEXT NOT NULL DEFAULT '[]',
                    shipping_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_toybox_orders_source_external
                    ON toybox_orders(source, external_order_id);

                CREATE TABLE IF NOT EXISTS toybox_queue (
                    id TEXT PRIMARY KEY,
                    order_id TEXT,
                    mapping_id TEXT,
                    printer_id TEXT,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    model_path TEXT NOT NULL DEFAULT '',
                    gcode_path TEXT NOT NULL DEFAULT '',
                    label_path TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_toybox_queue_status_updated
                    ON toybox_queue(status, updated_at DESC);

                CREATE TABLE IF NOT EXISTS toybox_webhook_events (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    external_order_id TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    received_at TEXT NOT NULL,
                    UNIQUE(provider, event_id)
                );
                """
            )

    def dashboard_summary(self) -> dict[str, object]:
        with self.database.connect() as connection:
            order_counts = _count_by_status(connection, "toybox_orders")
            queue_counts = _count_by_status(connection, "toybox_queue")
            printer_counts = _count_by_status(connection, "toybox_printers")
            mapping_counts = _count_by_status(connection, "toybox_product_mappings")
            webhook_count = int(connection.execute("SELECT COUNT(*) FROM toybox_webhook_events").fetchone()[0])
        return {
            "orders": order_counts,
            "queue": queue_counts,
            "printers": printer_counts,
            "mappings": mapping_counts,
            "webhooks": {"received": webhook_count},
            "blocked_queue": int(queue_counts.get("blocked", 0)),
            "open_orders": sum(int(order_counts.get(status, 0)) for status in ("new", "mapped", "queued", "printing", "blocked")),
            "ready_mappings": int(mapping_counts.get("ready", 0)),
        }

    def list_printers(self) -> list[ToyBoxPrinterProfileRecord]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM toybox_printers ORDER BY role, name").fetchall()
        return [self._printer_from_row(row) for row in rows]

    def upsert_printer(self, payload: ToyBoxPrinterProfileCreate) -> ToyBoxPrinterProfileRecord:
        now = utc_now()
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM toybox_printers WHERE name = ? AND role = ?",
                (payload.name, payload.role),
            ).fetchone()
            if existing is None:
                printer = ToyBoxPrinterProfileRecord(
                    id=f"tbp_{uuid4().hex}",
                    created_at=now,
                    updated_at=now,
                    **payload.model_dump(),
                )
                connection.execute(
                    """
                    INSERT INTO toybox_printers (
                        id, name, kind, role, bridge_tool_id, slicer_profile, camera_url,
                        status, metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        printer.id,
                        printer.name,
                        printer.kind,
                        printer.role,
                        printer.bridge_tool_id,
                        printer.slicer_profile,
                        printer.camera_url,
                        printer.status,
                        _json_dump(printer.metadata),
                        printer.created_at.isoformat(),
                        printer.updated_at.isoformat(),
                    ),
                )
                return printer
            data = self._printer_from_row(existing).model_dump()
            data.update(payload.model_dump())
            data["id"] = existing["id"]
            data["created_at"] = datetime.fromisoformat(existing["created_at"])
            data["updated_at"] = now
            printer = ToyBoxPrinterProfileRecord(**data)
            connection.execute(
                """
                UPDATE toybox_printers
                SET kind = ?, bridge_tool_id = ?, slicer_profile = ?, camera_url = ?,
                    status = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    printer.kind,
                    printer.bridge_tool_id,
                    printer.slicer_profile,
                    printer.camera_url,
                    printer.status,
                    _json_dump(printer.metadata),
                    printer.updated_at.isoformat(),
                    printer.id,
                ),
            )
        return printer

    def list_mappings(self) -> list[ToyBoxProductMappingRecord]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM toybox_product_mappings ORDER BY sku").fetchall()
        return [self._mapping_from_row(row) for row in rows]

    def upsert_mapping(self, payload: ToyBoxProductMappingCreate) -> ToyBoxProductMappingRecord:
        now = utc_now()
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM toybox_product_mappings WHERE sku = ?",
                (payload.sku,),
            ).fetchone()
            if existing is None:
                mapping = ToyBoxProductMappingRecord(
                    id=f"tbm_{uuid4().hex}",
                    created_at=now,
                    updated_at=now,
                    **payload.model_dump(),
                )
                connection.execute(
                    """
                    INSERT INTO toybox_product_mappings (
                        id, sku, title, model_path, slicer_profile, default_printer_id,
                        material, color, status, metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mapping.id,
                        mapping.sku,
                        mapping.title,
                        mapping.model_path,
                        mapping.slicer_profile,
                        mapping.default_printer_id,
                        mapping.material,
                        mapping.color,
                        mapping.status,
                        _json_dump(mapping.metadata),
                        mapping.created_at.isoformat(),
                        mapping.updated_at.isoformat(),
                    ),
                )
                return mapping
            data = self._mapping_from_row(existing).model_dump()
            data.update(payload.model_dump())
            data["id"] = existing["id"]
            data["created_at"] = datetime.fromisoformat(existing["created_at"])
            data["updated_at"] = now
            mapping = ToyBoxProductMappingRecord(**data)
            connection.execute(
                """
                UPDATE toybox_product_mappings
                SET title = ?, model_path = ?, slicer_profile = ?, default_printer_id = ?,
                    material = ?, color = ?, status = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    mapping.title,
                    mapping.model_path,
                    mapping.slicer_profile,
                    mapping.default_printer_id,
                    mapping.material,
                    mapping.color,
                    mapping.status,
                    _json_dump(mapping.metadata),
                    mapping.updated_at.isoformat(),
                    mapping.id,
                ),
            )
        return mapping

    def list_orders(self, limit: int = 100) -> list[ToyBoxOrderRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM toybox_orders ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._order_from_row(row) for row in rows]

    def upsert_order(self, payload: ToyBoxOrderCreate) -> ToyBoxOrderRecord:
        now = utc_now()
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM toybox_orders WHERE source = ? AND external_order_id = ?",
                (payload.source, payload.external_order_id),
            ).fetchone()
            if existing is None:
                order = ToyBoxOrderRecord(
                    id=f"tbo_{uuid4().hex}",
                    created_at=now,
                    updated_at=now,
                    **payload.model_dump(),
                )
                connection.execute(
                    """
                    INSERT INTO toybox_orders (
                        id, source, external_order_id, status, items_json, shipping_json,
                        metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order.id,
                        order.source,
                        order.external_order_id,
                        order.status,
                        _json_dump(order.items),
                        _json_dump(order.shipping),
                        _json_dump(order.metadata),
                        order.created_at.isoformat(),
                        order.updated_at.isoformat(),
                    ),
                )
                return order
            data = self._order_from_row(existing).model_dump()
            data.update(payload.model_dump())
            data["id"] = existing["id"]
            data["created_at"] = datetime.fromisoformat(existing["created_at"])
            data["updated_at"] = now
            order = ToyBoxOrderRecord(**data)
            connection.execute(
                """
                UPDATE toybox_orders
                SET status = ?, items_json = ?, shipping_json = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    order.status,
                    _json_dump(order.items),
                    _json_dump(order.shipping),
                    _json_dump(order.metadata),
                    order.updated_at.isoformat(),
                    order.id,
                ),
            )
        return order

    def record_webhook_event(
        self,
        provider: str,
        event_id: str,
        topic: str,
        external_order_id: str,
        metadata: dict | None = None,
    ) -> bool:
        now = utc_now()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO toybox_webhook_events (
                    id, provider, event_id, topic, external_order_id, metadata_json, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"tbw_{uuid4().hex}",
                    provider,
                    event_id,
                    topic,
                    external_order_id,
                    _json_dump(metadata or {}),
                    now.isoformat(),
                ),
            )
        return cursor.rowcount == 1

    def queue_order(self, order_id: str) -> list[ToyBoxQueueItemRecord]:
        order = self.get_order(order_id)
        mappings = {mapping.sku: mapping for mapping in self.list_mappings()}
        created: list[ToyBoxQueueItemRecord] = []
        missing_mapping = False

        for item in order.items:
            if not isinstance(item, dict):
                continue
            sku = str(item.get("sku") or item.get("variant_sku") or "").strip()
            quantity = _positive_int(item.get("quantity"), default=1)
            title = str(item.get("title") or item.get("name") or sku or "ToyBox3D print").strip()
            mapping = mappings.get(sku)
            if mapping is None:
                missing_mapping = True
                for copy_index in range(quantity):
                    created.append(
                        self.create_queue_item(
                            ToyBoxQueueItemCreate(
                                order_id=order.id,
                                title=f"{title} #{copy_index + 1}" if quantity > 1 else title,
                                status="blocked",
                                metadata={
                                    "reason": "missing_product_mapping",
                                    "sku": sku,
                                    "source_item": item,
                                },
                            )
                        )
                    )
                continue

            for copy_index in range(quantity):
                created.append(
                    self.create_queue_item(
                        ToyBoxQueueItemCreate(
                            order_id=order.id,
                            mapping_id=mapping.id,
                            printer_id=mapping.default_printer_id,
                            title=f"{mapping.title} #{copy_index + 1}" if quantity > 1 else mapping.title,
                            status="queued",
                            model_path=mapping.model_path,
                            metadata={
                                "sku": sku,
                                "source_item": item,
                                "material": mapping.material,
                                "color": mapping.color,
                                "slicer_profile": mapping.slicer_profile,
                            },
                        )
                    )
                )

        self._set_order_status(order.id, "blocked" if missing_mapping else "queued")
        return created

    def list_queue(self, limit: int = 100) -> list[ToyBoxQueueItemRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM toybox_queue ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._queue_from_row(row) for row in rows]

    def create_queue_item(self, payload: ToyBoxQueueItemCreate) -> ToyBoxQueueItemRecord:
        now = utc_now()
        item = ToyBoxQueueItemRecord(
            id=f"tbq_{uuid4().hex}",
            created_at=now,
            updated_at=now,
            **payload.model_dump(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO toybox_queue (
                    id, order_id, mapping_id, printer_id, title, status,
                    model_path, gcode_path, label_path, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.order_id,
                    item.mapping_id,
                    item.printer_id,
                    item.title,
                    item.status,
                    item.model_path,
                    item.gcode_path,
                    item.label_path,
                    _json_dump(item.metadata),
                    item.created_at.isoformat(),
                    item.updated_at.isoformat(),
                ),
            )
        return item

    def update_queue_status(self, item_id: str, payload: ToyBoxQueueStatusUpdate) -> ToyBoxQueueItemRecord:
        current = self.get_queue_item(item_id)
        metadata = {**current.metadata, **payload.metadata}
        if payload.detail:
            metadata["last_detail"] = payload.detail
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE toybox_queue SET status = ?, metadata_json = ?, updated_at = ? WHERE id = ?",
                (payload.status, _json_dump(metadata), now.isoformat(), item_id),
            )
        return self.get_queue_item(item_id)

    def get_queue_item(self, item_id: str) -> ToyBoxQueueItemRecord:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM toybox_queue WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise ToyBoxNotFoundError(item_id)
        return self._queue_from_row(row)

    def get_order(self, order_id: str) -> ToyBoxOrderRecord:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM toybox_orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise ToyBoxNotFoundError(order_id)
        return self._order_from_row(row)

    def _set_order_status(self, order_id: str, status: str) -> None:
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE toybox_orders SET status = ?, updated_at = ? WHERE id = ?",
                (status, now.isoformat(), order_id),
            )

    def _printer_from_row(self, row: sqlite3.Row) -> ToyBoxPrinterProfileRecord:
        return ToyBoxPrinterProfileRecord(
            id=row["id"],
            name=row["name"],
            kind=row["kind"],
            role=row["role"],
            bridge_tool_id=row["bridge_tool_id"],
            slicer_profile=row["slicer_profile"],
            camera_url=row["camera_url"],
            status=row["status"],
            metadata=_json_load(row["metadata_json"], {}),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _mapping_from_row(self, row: sqlite3.Row) -> ToyBoxProductMappingRecord:
        return ToyBoxProductMappingRecord(
            id=row["id"],
            sku=row["sku"],
            title=row["title"],
            model_path=row["model_path"],
            slicer_profile=row["slicer_profile"],
            default_printer_id=row["default_printer_id"],
            material=row["material"],
            color=row["color"],
            status=row["status"],
            metadata=_json_load(row["metadata_json"], {}),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _order_from_row(self, row: sqlite3.Row) -> ToyBoxOrderRecord:
        return ToyBoxOrderRecord(
            id=row["id"],
            source=row["source"],
            external_order_id=row["external_order_id"],
            status=row["status"],
            items=_json_load(row["items_json"], []),
            shipping=_json_load(row["shipping_json"], {}),
            metadata=_json_load(row["metadata_json"], {}),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _queue_from_row(self, row: sqlite3.Row) -> ToyBoxQueueItemRecord:
        return ToyBoxQueueItemRecord(
            id=row["id"],
            order_id=row["order_id"],
            mapping_id=row["mapping_id"],
            printer_id=row["printer_id"],
            title=row["title"],
            status=row["status"],
            model_path=row["model_path"],
            gcode_path=row["gcode_path"],
            label_path=row["label_path"],
            metadata=_json_load(row["metadata_json"], {}),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


def _json_dump(value) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _json_load(raw: str, fallback):
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def _positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 1)


def _count_by_status(connection: sqlite3.Connection, table: str) -> dict[str, int]:
    rows = connection.execute(f"SELECT status, COUNT(*) AS count FROM {table} GROUP BY status").fetchall()
    return {str(row["status"]): int(row["count"]) for row in rows}
