from sololicense.domain.models import FaultMode, RefundRequest
from sololicense.services import economics


def _levels(harness):
    return {k: int(harness.license_service.get_or_create(k).effective_level)
            for k in ("refund", "store_credit")}


def test_caught_fault_costs_a_review_not_a_loss(harness):
    harness.worker.run_refund(RefundRequest("ORD-1001", "Ada", 10.0, "x"))
    harness.fault_injector.arm("refund", FaultMode.QUIET_FAILURE)
    harness.worker.run_refund(RefundRequest("ORD-1002", "Grace", 10.0, "x"))

    report = economics.workspace_economics(harness.conn, _levels(harness), {})
    refund = report["classes"][0]

    assert refund["incidents"] == 1
    assert refund["leaked"] == 0
    assert refund["level"] == 0  # demoted -> nothing runs unattended
    assert refund["risk_cost_month"] == 0
    assert refund["supervision_saved_month"] == 0


def test_earned_l2_saves_money_with_smoothed_rate(harness):
    for order in ("ORD-1001", "ORD-1002"):
        harness.worker.run_refund(RefundRequest(order, "x", 10.0, "x"))

    report = economics.workspace_economics(harness.conn, _levels(harness), {})
    refund = report["classes"][0]

    assert refund["incident_rate"] < 0.02
    assert refund["net_saved_month"] > 0
