"""Order import/export as CSV - the zero-setup connector.

Any shop can export orders from Shopify, WooCommerce, Gumroad, a spreadsheet or
its own database as CSV. Column names are matched loosely ("Order #", "Total",
"Email", "Created at" …) so most exports load without editing.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime

from sololicense.connectors.base import OrderRecord

MAX_ROWS = 5000

# Accepted header spellings, normalised to lowercase letters and digits only.
_ALIASES = {
    "order_id": ("orderid", "order", "ordernumber", "orderno", "name", "id", "number", "invoice", "invoiceid"),
    "customer": ("customer", "customername", "billingname", "fullname", "buyer", "client"),
    "email": ("email", "customeremail", "emailaddress", "buyeremail"),
    "amount": ("amount", "total", "ordertotal", "price", "totalprice", "grandtotal", "paid", "amountpaid"),
    "ordered_at": ("orderedat", "date", "orderdate", "createdat", "created", "paidat", "purchasedate"),
    "currency": ("currency",),
}
_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,31}$")


def _key(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


def _match_columns(headers: list[str]) -> dict[str, str]:
    by_key = {_key(h): h for h in headers}
    found: dict[str, str] = {}
    for field, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in by_key and by_key[alias] not in found.values():
                found[field] = by_key[alias]
                break
    # "Name" is the order number in Shopify exports, but the customer's name in
    # a sheet that also has an explicit order column.
    if "name" in by_key and found.get("order_id") == by_key["name"] and "customer" not in found:
        explicit = [by_key[a] for a in _ALIASES["order_id"] if a != "name" and a in by_key]
        if explicit:
            found["customer"] = by_key["name"]
            found["order_id"] = explicit[0]
    return found


def _money(text: str) -> float:
    cleaned = re.sub(r"[^0-9.,-]", "", text or "")
    if cleaned.count(",") and cleaned.count("."):
        cleaned = cleaned.replace(",", "")
    elif cleaned.count(",") == 1 and len(cleaned.split(",")[1]) == 2:
        cleaned = cleaned.replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    return round(float(cleaned), 2)


def _date(text: str) -> str | None:
    text = (text or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:19], fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def parse_orders_csv(text: str) -> tuple[list[OrderRecord], list[str]]:
    """Parse CSV text into orders. Returns ``(orders, problems)``; a bad row is
    reported and skipped rather than failing the whole file."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames:
        return [], ["The file is empty."]
    columns = _match_columns(reader.fieldnames)
    missing = [f for f in ("order_id", "amount") if f not in columns]
    if missing:
        return [], [f"Could not find a column for: {', '.join(missing)}. Found: {', '.join(reader.fieldnames)}."]

    orders: list[OrderRecord] = []
    problems: list[str] = []
    seen: set[str] = set()
    for line, row in enumerate(reader, start=2):
        if len(orders) >= MAX_ROWS:
            problems.append(f"Stopped after {MAX_ROWS} orders.")
            break
        order_id = re.sub(r"[^A-Za-z0-9-]", "", (row.get(columns["order_id"]) or "").strip().replace("#", "")).upper()
        if not _ID_RE.match(order_id):
            problems.append(f"Row {line}: order number '{row.get(columns['order_id'])}' is not usable.")
            continue
        if order_id in seen:
            continue  # Shopify exports repeat the order on every line item
        try:
            amount = _money(row.get(columns["amount"], ""))
        except ValueError:
            problems.append(f"Row {line}: amount '{row.get(columns['amount'])}' is not a number.")
            continue
        if amount <= 0:
            problems.append(f"Row {line}: amount must be above zero.")
            continue
        email = (row.get(columns.get("email", ""), "") or "").strip() or None
        customer = (row.get(columns.get("customer", ""), "") or "").strip() or email or "Customer"
        seen.add(order_id)
        orders.append(OrderRecord(
            order_id=order_id,
            customer=customer[:80],
            amount=amount,
            email=email,
            ordered_at=_date(row.get(columns.get("ordered_at", ""), "")),
            currency=((row.get(columns.get("currency", ""), "") or "usd").strip().lower() or "usd")[:3],
            source="csv",
        ))
    return orders, problems


EXPORT_COLUMNS = ("order_id", "customer", "email", "ordered_at", "currency", "amount",
                  "refunded_amount", "credit_issued", "source", "external_id")


def orders_to_csv(rows: list[dict]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k) for k in EXPORT_COLUMNS})
    return out.getvalue()
