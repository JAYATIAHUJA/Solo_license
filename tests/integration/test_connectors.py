"""Connectors: CSV import and the Stripe connector against a mock Stripe API."""

from __future__ import annotations

import json
from urllib.parse import parse_qs

import httpx
import pytest

from sololicense.connectors.base import ConnectorError
from sololicense.connectors.csv_import import orders_to_csv, parse_orders_csv
from sololicense.connectors.stripe import StripeConnector, key_mode, order_id_for
from sololicense.domain.license import Decision
from sololicense.security import Actor, Role
from sololicense.services.policy_gate import PolicyGate

SHOPIFY = """Name,Email,Financial Status,Paid at,Total,Lineitem name,Billing Name
#1001,ada@example.com,paid,2026-10-01 10:00:00 +0000,25.00,Keyboard,Ada Lovelace
#1001,ada@example.com,paid,2026-10-01 10:00:00 +0000,25.00,Cable,Ada Lovelace
#1002,grace@example.com,paid,2026-10-02 11:00:00 +0000,"1,040.50",Desk,Grace Hopper
"""


def test_shopify_export_loads_without_editing():
    orders, problems = parse_orders_csv(SHOPIFY)
    assert problems == []
    assert [(o.order_id, o.customer, o.amount, o.email, o.ordered_at) for o in orders] == [
        ("1001", "Ada Lovelace", 25.0, "ada@example.com", "2026-10-01"),
        ("1002", "Grace Hopper", 1040.5, "grace@example.com", "2026-10-02"),
    ]


def test_bad_rows_are_reported_not_fatal():
    orders, problems = parse_orders_csv("order_id,amount\nA-100,12\n??,5\nB-200,abc\nC-300,-3\n")
    assert [o.order_id for o in orders] == ["A-100"]
    assert len(problems) == 3


def test_missing_columns_are_explained():
    orders, problems = parse_orders_csv("foo,bar\n1,2\n")
    assert orders == [] and "order_id" in problems[0]


def test_export_round_trips():
    orders, _ = parse_orders_csv(SHOPIFY)
    text = orders_to_csv([o.__dict__ for o in orders])
    again, _ = parse_orders_csv(text)
    assert [o.order_id for o in again] == ["1001", "1002"]


def test_csv_import_through_the_api_flow(harness):
    from sololicense.db.repositories import orders as orders_repo

    orders, _ = parse_orders_csv(SHOPIFY)
    added, updated = orders_repo.upsert_orders(harness.conn, orders)
    assert (added, updated) == (2, 0)
    assert orders_repo.get_order(harness.conn, "1002")["source"] == "csv"


# --- Stripe -------------------------------------------------------------------


class FakeStripe:
    """Just enough of Stripe's API: charges, refunds, customer balance, idempotency."""

    def __init__(self, *, drop_first_refund=False):
        self.charge = {"id": "ch_123ABC", "amount": 4000, "amount_refunded": 0, "currency": "usd",
                       "paid": True, "status": "succeeded", "created": 1760000000,
                       "metadata": {"order_id": "ord-77"}, "billing_details": {"name": None, "email": None},
                       "receipt_email": "grace@example.com",
                       "customer": {"id": "cus_1", "name": "Grace Hopper", "email": "grace@example.com"}}
        self.balance = []
        self.seen_keys = {}
        self.calls = []
        self.drop_first_refund = drop_first_refund

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path, request.headers.get("Idempotency-Key")))
        assert request.headers["Authorization"] == "Bearer sk_test_abc"
        key = request.headers.get("Idempotency-Key")
        if key and key in self.seen_keys:
            return httpx.Response(200, json=self.seen_keys[key])
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        path = request.url.path
        if path == "/v1/balance":
            return httpx.Response(200, json={"object": "balance"})
        if path == "/v1/charges" and request.method == "GET":
            return httpx.Response(200, json={"data": [self.charge]})
        if path == "/v1/charges/ch_123ABC":
            return httpx.Response(200, json=self.charge)
        if path == "/v1/refunds":
            amount = int(form["amount"])
            if amount > self.charge["amount"] - self.charge["amount_refunded"]:
                return httpx.Response(400, json={"error": {"message": "Refund exceeds charge"}})
            body = {"id": f"re_{len(self.calls)}", "status": "succeeded"}
            if self.drop_first_refund:
                self.drop_first_refund = False   # the response "succeeds" but nothing lands
                return httpx.Response(200, json=body)
            self.charge["amount_refunded"] += amount
            self.seen_keys[key] = body
            return httpx.Response(200, json=body)
        if path == "/v1/customers/cus_1/balance_transactions":
            if request.method == "GET":
                return httpx.Response(200, json={"data": self.balance})
            txn = {"id": f"cbtxn_{len(self.balance)}", "amount": int(form["amount"]),
                   "metadata": {"order_id": form["metadata[order_id]"]}}
            self.balance.append(txn)
            self.seen_keys[key] = txn
            return httpx.Response(200, json=txn)
        return httpx.Response(404, json={"error": {"message": f"no route {path}"}})


def _connector(fake, conn=None):
    return StripeConnector(
        "sk_test_abc", conn=conn,
        client=httpx.Client(transport=httpx.MockTransport(fake.handler)),
    )


def _permit(harness, task_class, order_id, amount):
    return PolicyGate(harness.conn).issue(
        policy=harness.worker._policy_service.active(),
        task_class=task_class, tool=task_class, order_id=order_id, amount=amount,
        authorized=Decision.AUTO_EXECUTE, attempted=Decision.AUTO_EXECUTE,
        license_level=2, approved=False, actor=Actor("test:stripe", Role.ADMIN),
    )


def test_key_checks():
    assert key_mode("sk_test_123") == "test" and key_mode("rk_live_9") == "live" and key_mode("pk_test_1") is None
    with pytest.raises(ConnectorError):
        StripeConnector("sk_live_123")
    with pytest.raises(ConnectorError):
        StripeConnector("hello")


def test_charges_become_orders():
    fake = FakeStripe()
    [order] = _connector(fake).list_orders()
    assert order.order_id == "ORD-77" and order.amount == 40.0 and order.customer == "Grace Hopper"
    assert order.external_id == "ch_123ABC" and order.customer_ref == "cus_1" and order.source == "stripe"
    assert order_id_for({"id": "ch_3Nabcdefghijklmn", "metadata": {}}).startswith("ST-")


def test_refund_is_verified_from_stripe_not_from_the_response(harness):
    fake = FakeStripe()
    stripe = _connector(fake, harness.conn)
    order = {"order_id": "ORD-77", "external_id": "ch_123ABC", "customer_ref": "cus_1", "currency": "usd"}
    result = stripe.apply("refund", order, 10.0, idempotency_key="k1", permit=_permit(harness, "refund", "ORD-77", 10.0))
    assert result.ok and stripe.read_effect("refund", order) == 10.0
    # A replay cannot reach Stripe without a fresh, server-issued permit.
    with pytest.raises(ConnectorError, match="permit"):
        stripe.apply("refund", order, 10.0, idempotency_key="k1")
    assert stripe.read_effect("refund", order) == 10.0


def test_store_credit_is_a_customer_balance_credit(harness):
    fake = FakeStripe()
    stripe = _connector(fake, harness.conn)
    order = {"order_id": "ORD-77", "external_id": "ch_123ABC", "customer_ref": "cus_1", "currency": "usd"}
    stripe.apply("store_credit", order, 7.5, idempotency_key="c1", permit=_permit(harness, "store_credit", "ORD-77", 7.5))
    assert fake.balance[0]["amount"] == -750
    assert stripe.read_effect("store_credit", order) == 7.5


def test_stripe_errors_are_honest_refusals(harness):
    fake = FakeStripe()
    stripe = _connector(fake, harness.conn)
    order = {"order_id": "ORD-77", "external_id": "ch_123ABC", "customer_ref": "cus_1", "currency": "usd"}
    with pytest.raises(ConnectorError, match="exceeds"):
        stripe.apply("refund", order, 999.0, idempotency_key="k2", permit=_permit(harness, "refund", "ORD-77", 999.0))


def test_worker_recovers_a_lost_stripe_refund(harness):
    """Stripe answers 'succeeded' but nothing lands; the read-back catches it,
    the agent retries with the same key and verifies against Stripe."""
    from sololicense.connectors import Connectors
    from sololicense.db.repositories import orders as orders_repo
    from sololicense.domain.models import RefundRequest, RunStatus

    fake = FakeStripe(drop_first_refund=True)
    stripe = _connector(fake, harness.conn)
    orders_repo.upsert_orders(harness.conn, stripe.list_orders())
    harness.conn.commit()

    class Fixed(Connectors):
        def stripe(self):
            return stripe

    harness.worker._connectors = Fixed(harness.conn, harness.config)
    result = harness.worker.run_refund(RefundRequest("ORD-77", "Grace", 20.0, "broken"), idempotency_key="t-1")
    assert result.recovered and result.status is RunStatus.DEMOTED
    assert fake.charge["amount_refunded"] == 2000
    refund_calls = [c for c in fake.calls if c[1] == "/v1/refunds"]
    assert [c[2] for c in refund_calls] == ["t-1", "t-1"]
    # The app shows what Stripe shows.
    assert orders_repo.get_refunded_amount(harness.conn, "ORD-77") == 20.0
    assert json.loads(json.dumps(result.detections[0].rule)) == "state_mismatch"
