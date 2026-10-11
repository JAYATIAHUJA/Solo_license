"""The built-in store: orders and their side effects live in SQLite.

Used for sample data and CSV-imported orders. ``suppress_write`` exists for the
fault switch: the write is skipped but the tool still reports success — the
exact lie verification is built to catch."""

from __future__ import annotations

import sqlite3

from sololicense.connectors.base import OrderRecord, ToolResult
from sololicense.db.repositories import orders as orders_repo
from sololicense.domain.task_classes import get_spec


class LocalConnector:
    name = "local"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def apply(
        self, task_class: str, order: dict, amount: float, *, idempotency_key: str, suppress_write: bool = False
    ) -> ToolResult:
        if suppress_write:
            return ToolResult(ok=True, message="Processed (reported).")
        orders_repo.apply_effect(self._conn, order["order_id"], get_spec(task_class).effect_column, amount)
        return ToolResult(ok=True, message="Processed.", reference=idempotency_key)

    def read_effect(self, task_class: str, order: dict) -> float:
        return orders_repo.get_effect_amount(self._conn, order["order_id"], get_spec(task_class).effect_column)

    def list_orders(self) -> list[OrderRecord]:
        return [
            OrderRecord(
                order_id=row["order_id"], customer=row["customer"], amount=float(row["amount"]),
                email=row["email"], ordered_at=row["ordered_at"], source=row["source"],
            )
            for row in orders_repo.list_orders(self._conn)
        ]
