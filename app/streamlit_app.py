"""Solo License — one-screen live control room.

Everything a judge needs in a single view: the autonomy dial, the controls
(trigger a refund, inject a fault, restore the license), the recent-runs feed,
and the evidence packet used to restore. Every action writes through the real
agent and re-reads state from SQLite, so the dial is always live.

Run with:  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import streamlit as st

from sololicense.bootstrap import AppContext, build_app
from sololicense.db.repositories import detections as detections_repo
from sololicense.db.repositories import events as events_repo
from sololicense.db.repositories import license as license_repo
from sololicense.db.repositories import orders as orders_repo
from sololicense.db.repositories import runs as runs_repo
from sololicense.db.seed import seed
from sololicense.domain.license import LicenseLevel
from sololicense.domain.models import FaultMode, RefundRequest
from sololicense.services.evidence import build_packet

TASK_CLASS = "refund"
_STATUS_ICON = {
    "clean": "🟢", "demoted": "🔴", "suggested": "🟡", "pending_approval": "🟠",
}
_FAULT_LABELS = {
    FaultMode.NONE: "None (run normally)",
    FaultMode.QUIET_FAILURE: "Quiet failure — tool 'succeeds', SQLite unchanged",
    FaultMode.POLICY_VIOLATION: "Policy violation — act beyond the license",
}


@st.cache_resource
def get_app() -> AppContext:
    """Build the wired app once per server process (shared across reruns)."""
    app = build_app(check_same_thread=False)
    # First-run convenience: seed if the orders table is empty.
    if not orders_repo.list_orders(app.conn):
        seed(app.conn, app.config)
    return app


def render_dial(app: AppContext) -> None:
    state = app.license_service.get_or_create(TASK_CLASS)
    eff = state.effective_level
    st.subheader("Autonomy dial · task class `refund`")

    cols = st.columns(4)
    for i, level in enumerate(LicenseLevel):
        active = level == eff
        with cols[i]:
            marker = "✅" if active else "▫️"
            color = "#e74c3c" if (active and state.quarantined) else (
                "#2ecc71" if active else "#95a5a6")
            st.markdown(
                f"<div style='text-align:center;border-radius:8px;padding:8px;"
                f"border:2px solid {color};opacity:{'1' if active else '0.5'}'>"
                f"<div style='font-size:1.3rem'>{marker} <b>{level.name}</b></div>"
                f"<div style='font-size:0.8rem'>{level.label}</div></div>",
                unsafe_allow_html=True,
            )

    if state.quarantined:
        st.error(
            f"QUARANTINED — crashed from {state.demoted_from.name if state.demoted_from else '?'}"
            f". Acting at L0 (suggest only) until a human restores it.")
    else:
        need = app.config.promotion_clean_runs
        if state.level is LicenseLevel.L3:
            st.success("At L3 — full autonomy with post-hoc audit.")
        else:
            st.progress(
                min(state.consecutive_clean_runs / need, 1.0),
                text=f"{state.consecutive_clean_runs}/{need} clean runs toward "
                     f"{LicenseLevel(state.level + 1).name}",
            )


def render_controls(app: AppContext) -> None:
    st.sidebar.header("Controls")
    orders = orders_repo.list_orders(app.conn)
    labels = {
        f"{o['order_id']} · {o['customer']} · ${o['amount']:.2f}": o
        for o in orders
    }

    st.sidebar.subheader("1 · Trigger a refund")
    choice = st.sidebar.selectbox("Order", list(labels))
    order = labels[choice]
    ceiling = app.config.l2_auto_refund_ceiling
    hint = "under" if order["amount"] <= ceiling else "ABOVE"
    st.sidebar.caption(f"${order['amount']:.2f} is {hint} the L2 ceiling "
                       f"(${ceiling:.0f}).")
    if st.sidebar.button("Run refund", type="primary", use_container_width=True):
        result = app.worker.run_refund(
            RefundRequest(order["order_id"], order["customer"],
                          float(order["amount"]), "customer refund"))
        st.session_state["selected_run"] = result.run_id
        st.rerun()

    st.sidebar.subheader("2 · Inject a fault")
    armed = app.fault_injector.peek(TASK_CLASS)
    mode = st.sidebar.radio(
        "Arm for next run", list(FaultMode),
        format_func=lambda m: _FAULT_LABELS[m],
        index=list(FaultMode).index(armed))
    if st.sidebar.button("Arm fault", use_container_width=True):
        app.fault_injector.arm(TASK_CLASS, mode)
        st.rerun()
    if armed is not FaultMode.NONE:
        st.sidebar.warning(f"Armed: {armed.value} — fires on the next refund.")

    st.sidebar.subheader("3 · Restore the license")
    target = st.sidebar.selectbox(
        "Restore to", list(LicenseLevel), index=2,
        format_func=lambda lv: f"{lv.name} — {lv.label}")
    if st.sidebar.button("Restore license", use_container_width=True):
        app.license_service.restore_license(
            TASK_CLASS, target, reason="Human restored after evidence review.")
        st.rerun()

    st.sidebar.divider()
    if st.sidebar.button("Reseed demo", use_container_width=True):
        seed(app.conn, app.config)
        st.session_state.pop("selected_run", None)
        st.rerun()


def render_runs(app: AppContext) -> None:
    st.subheader("Recent runs")
    rows = runs_repo.list_recent(app.conn, limit=12)
    if not rows:
        st.caption("No runs yet — trigger a refund from the sidebar.")
        return
    table = [{
        "run": r["id"],
        "": _STATUS_ICON.get(r["status"], ""),
        "status": r["status"],
        "order": r["order_id"],
        "amount": f"${r['requested_amount']:.2f}",
        "authorized": r["decision"],
        "Δ refunded": f"${r['after_refunded'] - r['before_refunded']:.2f}",
        "fault": r["fault_mode"],
        "trace": (r["trace_id"] or "")[:8],
    } for r in rows]
    st.dataframe(table, use_container_width=True, hide_index=True)

    ids = [r["id"] for r in rows]
    default = st.session_state.get("selected_run", ids[0])
    st.session_state["selected_run"] = st.selectbox(
        "Inspect run (evidence packet)", ids,
        index=ids.index(default) if default in ids else 0)


def render_evidence(app: AppContext) -> None:
    run_id = st.session_state.get("selected_run")
    if run_id is None:
        return
    packet = build_packet(app.conn, run_id, app.config)
    if packet is None:
        return

    st.subheader(f"Evidence packet · run #{run_id}")
    c1, c2, c3 = st.columns(3)
    c1.metric("refunded before", f"${packet.before_refunded:.2f}")
    c2.metric("refunded after", f"${packet.after_refunded:.2f}",
              delta=f"${packet.actual_delta:.2f}")
    c3.metric("intended", f"${packet.intended_delta:.2f}")

    if packet.detections:
        st.error("Detections (these drove the demotion):")
        for d in packet.detections:
            st.markdown(f"- **{d['rule']}** ({d['severity']}): {d['message']}")
    else:
        st.success("No detections on this run.")

    if packet.neatlogs_link:
        st.markdown(f"[Open trace in neatlogs]({packet.neatlogs_link})")
    else:
        st.caption(f"neatlogs offline — trace `{packet.run['trace_id']}` "
                   f"mirrored locally below.")

    with st.expander("Trace spans", expanded=False):
        st.dataframe([
            {"span": s["name"], "status": s["status"], **s["attributes"]}
            for s in packet.spans
        ], use_container_width=True, hide_index=True)

    with st.expander("License history (git-backed / Entire)", expanded=True):
        if not packet.license_history:
            st.caption("No license changes recorded yet.")
        for e in packet.license_history:
            sha = f"`{e['git_sha']}`" if e["git_sha"] else "(uncommitted)"
            st.markdown(
                f"- {sha} **{e['kind']}** L{e['from_level']} → L{e['to_level']}"
                f" — {e['reason']}")


def main() -> None:
    st.set_page_config(page_title="Solo License", page_icon="🎚️", layout="wide")
    st.title("🎚️ Solo License")
    st.caption("An operations agent that earns unattended autonomy — and loses "
               "it the instant a detection fires.")

    app = get_app()
    render_controls(app)
    render_dial(app)
    st.divider()
    left, right = st.columns([1, 1])
    with left:
        render_runs(app)
    with right:
        render_evidence(app)


if __name__ == "__main__":
    main()
