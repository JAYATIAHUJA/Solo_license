"""Connectors: where orders come from and where side effects really land."""

from __future__ import annotations

import os
import sqlite3

from sololicense.config import Config
from sololicense.connectors.base import Connector, ConnectorError, OrderRecord, ToolResult
from sololicense.connectors.local import LocalConnector

__all__ = ["Connector", "ConnectorError", "Connectors", "OrderRecord", "ToolResult"]


class Connectors:
    """Picks the connector that owns an order. Stripe is built lazily, so a
    workspace without a Stripe key never needs one."""

    def __init__(self, conn: sqlite3.Connection, config: Config) -> None:
        self._conn = conn
        self._config = config
        self.local = LocalConnector(conn)
        self._stripe = None

    @property
    def stripe_configured(self) -> bool:
        return bool(self._config.stripe_secret_key)

    def stripe(self):
        if self._stripe is None:
            if not self.stripe_configured:
                raise ConnectorError("Connect Stripe in Settings first.")
            from sololicense.connectors.stripe import StripeConnector

            self._stripe = StripeConnector(
                self._config.stripe_secret_key,
                api_base=self._config.stripe_api_base,
                allow_live=os.environ.get("SOLO_ALLOW_LIVE_STRIPE", "") == "1",
            )
        return self._stripe

    def for_order(self, order) -> Connector:
        if order["source"] == "stripe":
            return self.stripe()
        return self.local
