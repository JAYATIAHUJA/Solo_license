# Policy Governance Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Solo License govern autonomous writes with immutable, versioned policies and server-side execution permits, then surface the governing policy and its measurable promotion evidence.

**Architecture:** Add an immutable policy aggregate plus SQLite repositories for policy versions, policy impact records, and single-use execution permits. The worker will request a permit from a policy gate before invoking a tool, and the tool will transactionally consume and validate that permit at its database-write boundary. Promotion becomes a policy-scoped evaluation rather than a global clean-run counter.

**Tech Stack:** Python 3.12, FastAPI, SQLite, React 19, Vite, pytest.

**Spec:** `docs/superpowers/specs/2026-10-11-policy-governance-foundation-design.md`

## Global Constraints

- Preserve the existing local refund/store-credit demo and its idempotency/read-back verification behavior.
- Do not pass, persist, trace, render, or log raw secrets.
- Existing databases must migrate idempotently and receive a default `v1` policy.
- An unauthorized attempt must not mutate `orders`.
- Policy changes cannot silently increase a license level.
- Run `python -m pytest` and `npm --prefix frontend run build` before reporting this milestone complete.

## Review Focus

- A permit for refund must be rejected by the store-credit tool, even for the same order and amount.
- An expired or previously consumed permit must leave the order unchanged.
- A policy activation immediately after a clean run must not let evidence from the older policy promote the class.
- A duplicate/idempotent request must not consume a second permit or create a second side effect.
- A malformed policy payload must be rejected before it creates any version or alters the active policy.

---

### Task 1: Immutable policy domain model and schema migration

**Files:**
- Create: `sololicense/domain/policy.py`
- Modify: `sololicense/db/schema.sql`
- Modify: `sololicense/db/database.py`
- Test: `tests/test_policy.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces `PolicyRule`, `PolicyVersion`, `PolicyImpact`, and `EvaluationProgress` immutable dataclasses.
- Produces `validate_rule(rule: PolicyRule) -> None` and `evaluate_runs(outcomes: Sequence[bool], rule: PolicyRule) -> EvaluationProgress`.
- Adds nullable `runs.policy_version` and tables `policies`, `policy_rules`, `policy_impacts`, and `execution_permits`.

- [ ] **Step 1: Write failing domain tests**

```python
def test_policy_rule_rejects_invalid_sample_and_pass_rate():
    with pytest.raises(ValueError):
        PolicyRule("refund", "refund", 2, 50, 0, 3, 1.0)

def test_evaluation_needs_minimum_samples_and_pass_rate():
    rule = PolicyRule("refund", "refund", 2, 50, 5, 3, 0.8)
    assert evaluate_runs([True, True], rule).eligible is False
    assert evaluate_runs([True, True, False], rule).eligible is False
    assert evaluate_runs([True, True, True], rule).eligible is True
```

- [ ] **Step 2: Run the targeted tests and verify they fail because `sololicense.domain.policy` does not exist**

Run: `.venv/bin/python -m pytest tests/test_policy.py -v`

- [ ] **Step 3: Implement the pure policy dataclasses and evaluation functions in `sololicense/domain/policy.py`**

Use decimal-safe rounding boundaries where comparisons require it; an evaluation window selects the most recent `rule.evaluation_window` boolean outcomes.

- [ ] **Step 4: Write failing migration tests for an existing legacy database**

```python
def test_apply_schema_adds_policy_version_and_policy_tables(tmp_path):
    conn = sqlite3.connect(tmp_path / "legacy.db")
    conn.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY)")
    apply_schema(conn)
    assert "policy_version" in columns(conn, "runs")
    assert table_exists(conn, "policies")
```

- [ ] **Step 5: Add idempotent policy tables and `runs.policy_version` migration**

Use `CREATE TABLE IF NOT EXISTS` in `schema.sql` and column discovery/`ALTER TABLE` in `database._migrate_runs`; create indexes for active-policy lookup, policy-version runs, and unconsumed permits.

- [ ] **Step 6: Run targeted tests and verify they pass**

Run: `.venv/bin/python -m pytest tests/test_policy.py tests/test_config.py -v`

- [ ] **Step 7: Commit the domain and migration change**

```bash
git add sololicense/domain/policy.py sololicense/db/schema.sql sololicense/db/database.py tests/test_policy.py tests/test_config.py
git commit -m "feat: add versioned policy schema"
```

### Task 2: Policy persistence, bootstrap default, and impact calculation

**Files:**
- Create: `sololicense/db/repositories/policies.py`
- Create: `sololicense/services/policy_service.py`
- Modify: `sololicense/bootstrap.py`
- Modify: `sololicense/db/repositories/runs.py`
- Test: `tests/test_policy_service.py`

**Interfaces:**
- Produces repository functions `active_policy(conn)`, `create_version(conn, policy, rules)`, `rules_for(conn, version)`, `list_versions(conn)`, and `insert_impacts(conn, impacts)`.
- Produces `PolicyService.ensure_default_policy() -> PolicyVersion`, `preview_activation(rules: tuple[PolicyRule, ...]) -> list[PolicyImpact]`, `activate(name: str, summary: str, rules: tuple[PolicyRule, ...], actor: Actor) -> PolicyVersion`, and `evaluation_for(task_class: str) -> EvaluationProgress`.
- `runs.list_verified_outcomes_for_policy(conn, task_class, policy_version, limit) -> list[bool]` returns newest-first outcomes only for persisted, verified executions.

- [ ] **Step 1: Write failing service tests for first-start defaults and immutable activation**

```python
def test_bootstrap_creates_v1_from_existing_refund_and_credit_settings(harness):
    policy = PolicyService(harness.conn, harness.config).ensure_default_policy()
    assert policy.version == 1
    assert policy.rule_for("refund").l2_ceiling == 50

def test_activate_creates_v2_and_preserves_v1_rules(harness):
    service = PolicyService(harness.conn, harness.config)
    v1 = service.ensure_default_policy()
    v2 = service.activate(changed_rules, actor=SYSTEM_ACTOR, summary="Tighter ceiling")
    assert v2.version == 2
    assert service.get(v1.version).rule_for("refund").l2_ceiling != v2.rule_for("refund").l2_ceiling
```

- [ ] **Step 2: Run the service tests and verify they fail because policy persistence is absent**

Run: `.venv/bin/python -m pytest tests/test_policy_service.py -v`

- [ ] **Step 3: Implement repository methods and `PolicyService`**

The default policy must be constructed from `Config.ceiling_for()` and the existing promotion threshold. Activation must validate all task classes and write impact rows in one database transaction; it supersedes the previous active policy only after all writes succeed.

- [ ] **Step 4: Wire `PolicyService` into `AppContext` and `build_app`**

Expose `policy_service` in `AppContext`; call `ensure_default_policy()` after settings overrides resolve and before creating the worker.

- [ ] **Step 5: Add failing tests for policy-scoped outcomes and impact records**

```python
def test_v2_does_not_count_clean_v1_runs_toward_v2_promotion(harness):
    # Persist clean v1 outcomes, activate v2, then evaluate v2.
    assert service.evaluation_for("refund").sample_size == 0

def test_activation_records_held_for_review_when_evidence_is_insufficient(harness):
    impacts = service.preview_activation(changed_rules)
    assert impacts[0].action == "hold_for_review"
```

- [ ] **Step 6: Run targeted tests and verify they pass**

Run: `.venv/bin/python -m pytest tests/test_policy.py tests/test_policy_service.py tests/test_config.py -v`

- [ ] **Step 7: Commit the policy service slice**

```bash
git add sololicense/db/repositories/policies.py sololicense/services/policy_service.py sololicense/bootstrap.py sololicense/db/repositories/runs.py tests/test_policy_service.py
git commit -m "feat: persist policy versions and impacts"
```

### Task 3: Single-use execution permits at the tool boundary

**Files:**
- Create: `sololicense/services/policy_gate.py`
- Create: `sololicense/db/repositories/permits.py`
- Modify: `sololicense/agent/tools.py`
- Modify: `sololicense/agent/worker.py`
- Modify: `sololicense/domain/models.py`
- Test: `tests/test_policy_gate.py`
- Test: `tests/test_refund_worker.py`

**Interfaces:**
- Produces `ExecutionPermit(token: str, policy_version: int, task_class: str, tool: str, order_id: str, amount: float, expires_at: datetime)` and `PermitRejected(ValueError)`.
- Produces `PolicyGate.issue(policy: PolicyVersion, task_class: str, tool: str, order_id: str, amount: float, authorized: Decision, attempted: Decision, actor: Actor) -> ExecutionPermit` and `PolicyGate.consume_for_write(permit: ExecutionPermit) -> None`.
- Changes `execute_refund(conn: sqlite3.Connection, *, order_id: str, amount: float, suppress_write: bool, permit: ExecutionPermit, column: str) -> ToolResult` so every write verifies/consumes its permit.

- [ ] **Step 1: Write a failing test that proves a forced unauthorized attempt cannot alter an order**

```python
def test_policy_violation_fault_is_blocked_before_the_database_write(harness):
    harness.fault_injector.arm("refund", FaultMode.POLICY_VIOLATION)
    before = orders_repo.get_refunded_amount(harness.conn, "ORD-1004")
    result = harness.worker.run_refund(RefundRequest("ORD-1004", "Katherine", 120, "big"))
    assert result.status is RunStatus.DEMOTED
    assert orders_repo.get_refunded_amount(harness.conn, "ORD-1004") == before
```

- [ ] **Step 2: Write failing permit invariant tests**

```python
def test_consumed_permit_cannot_execute_twice(policy_gate, conn):
    permit = issue_refund_permit(policy_gate)
    execute_refund(conn, order_id="ORD-1001", amount=10, suppress_write=False,
                   permit=permit, column="refunded_amount")
    with pytest.raises(PermitRejected, match="already used"):
        execute_refund(conn, order_id="ORD-1001", amount=10, suppress_write=False,
                       permit=permit, column="refunded_amount")

def test_permit_rejects_different_tool_or_amount(policy_gate, conn):
    permit = issue_refund_permit(policy_gate)
    with pytest.raises(PermitRejected):
        execute_refund(conn, order_id="ORD-1001", amount=20, suppress_write=False,
                       permit=permit, column="refunded_amount")
```

- [ ] **Step 3: Run the targeted tests and verify current code permits the fault write / lacks permit APIs**

Run: `.venv/bin/python -m pytest tests/test_policy_gate.py tests/test_refund_worker.py::test_policy_violation_above_ceiling_demotes -v`

- [ ] **Step 4: Implement digest-only permit persistence and transactional consumption**

Generate raw random tokens with `secrets.token_urlsafe`; persist only SHA-256 digests. The `UPDATE ... WHERE consumed_at IS NULL AND expires_at > now` condition must atomically consume exactly one matching permit before `orders_repo.apply_effect` executes.

- [ ] **Step 5: Route all executing worker paths through `PolicyGate` and the permit-aware tool adapter**

Keep the fault injector's attempted decision for observability, but make the gate return a blocked execution result if it disagrees with the policy. Persist the run/detection and demote the license without applying an order mutation.

- [ ] **Step 6: Run focused safety and regression tests**

Run: `.venv/bin/python -m pytest tests/test_policy_gate.py tests/test_refund_worker.py tests/test_api_idempotency.py tests/test_detections.py -v`

- [ ] **Step 7: Commit the permit-gate change**

```bash
git add sololicense/services/policy_gate.py sololicense/db/repositories/permits.py sololicense/agent/tools.py sololicense/agent/worker.py sololicense/domain/models.py tests/test_policy_gate.py tests/test_refund_worker.py
git commit -m "feat: enforce execution permits at tool boundary"
```

### Task 4: Policy-scoped promotion and run audit binding

**Files:**
- Modify: `sololicense/services/license_service.py`
- Modify: `sololicense/agent/worker.py`
- Modify: `sololicense/db/repositories/runs.py`
- Test: `tests/test_license_state_machine.py`
- Test: `tests/test_policy_service.py`

**Interfaces:**
- Changes `LicenseService.apply_clean_run(..., policy_version: int, evaluation: EvaluationProgress) -> Transition`.
- Changes `NewRun` to require `policy_version: int`.
- The worker obtains the active policy once per run and persists the exact policy version with the run.

- [ ] **Step 1: Write failing promotion tests using the evaluation window rather than consecutive count**

```python
def test_three_clean_runs_promote_only_when_current_policy_requires_three(harness):
    rule = policy_with(minimum_samples=3, evaluation_window=3, minimum_verified_pass_rate=1.0)
    # first two runs remain; third promotes

def test_one_failure_in_current_window_prevents_promotion_at_required_pass_rate(harness):
    rule = policy_with(minimum_samples=3, evaluation_window=3, minimum_verified_pass_rate=1.0)
    # clean, failure, clean -> no promotion
```

- [ ] **Step 2: Run the targeted tests and verify legacy consecutive-run logic fails them**

Run: `.venv/bin/python -m pytest tests/test_license_state_machine.py tests/test_policy_service.py -v`

- [ ] **Step 3: Implement policy-version persistence and policy-scoped promotion**

Keep `consecutive_clean_runs` as a backward-compatible displayed tally, but determine promotion from `PolicyService.evaluation_for()` at the active policy version. Include the sample size, pass rate, and policy version in the promotion ledger reason.

- [ ] **Step 4: Run worker/license regression tests**

Run: `.venv/bin/python -m pytest tests/test_refund_worker.py tests/test_license_state_machine.py tests/test_api_product.py -v`

- [ ] **Step 5: Commit policy-scoped promotion**

```bash
git add sololicense/services/license_service.py sololicense/agent/worker.py sololicense/db/repositories/runs.py tests/test_license_state_machine.py tests/test_policy_service.py
git commit -m "feat: evaluate autonomy by policy version"
```

### Task 5: Admin policy API and dashboard serialization

**Files:**
- Modify: `app/api.py`
- Modify: `tests/test_api_product.py`
- Create: `tests/test_api_policy.py`

**Interfaces:**
- Adds `GET /api/policies`, `POST /api/policies/preview`, `POST /api/policies`, and `GET /api/policy-impacts`.
- Adds policy/policy-evaluation fields to `dashboard_payload` and `serialize_settings`.
- Activation payload contains `name`, `summary`, and one validated rule per registered task class.

- [ ] **Step 1: Write failing API authorization and validation tests**

```python
def test_operator_cannot_activate_policy(client, operator_headers):
    assert client.post("/api/policies", headers=operator_headers, json=valid_policy()).status_code == 403

def test_admin_preview_does_not_create_a_version(client, admin_headers):
    preview = client.post("/api/policies/preview", headers=admin_headers, json=valid_policy())
    assert preview.status_code == 200
    assert client.get("/api/policies", headers=admin_headers).json()["active"]["version"] == 1
```

- [ ] **Step 2: Run API tests and verify endpoints are missing**

Run: `.venv/bin/python -m pytest tests/test_api_policy.py -v`

- [ ] **Step 3: Implement Pydantic request models and role-protected endpoints**

Validate every task class has one rule, no unregistered task/tool is accepted, numeric ranges are safe, and activation includes computed impact results in its response. Never return permit digests or secrets.

- [ ] **Step 4: Extend dashboard serialization with active policy and per-class evaluation progress**

Preserve existing dashboard response keys so current pages continue rendering.

- [ ] **Step 5: Run API test coverage**

Run: `.venv/bin/python -m pytest tests/test_api_policy.py tests/test_api_product.py tests/test_api_security.py -v`

- [ ] **Step 6: Commit the API slice**

```bash
git add app/api.py tests/test_api_policy.py tests/test_api_product.py
git commit -m "feat: expose versioned autonomy policies"
```

### Task 6: Policy review and activation interface

**Files:**
- Create: `frontend/src/features/app/components/PolicyEditor.jsx`
- Create: `frontend/src/features/app/components/policy-editor.css`
- Create: `frontend/src/features/app/components/policyForm.js`
- Modify: `frontend/src/lib/api.js`
- Modify: `frontend/src/features/app/pages/Settings.jsx`
- Modify: `frontend/src/features/app/pages/Overview.jsx`
- Test: `frontend/test/policyForm.test.js`

**Interfaces:**
- Adds `api.listPolicies()`, `api.previewPolicy(payload)`, `api.activatePolicy(payload)`, and `api.listPolicyImpacts()`.
- `PolicyEditor` receives `{ policy, taskClasses, onActivated }` and never receives secret settings.
- `policyForm.js` exports `draftFromPolicy(policy)`, `validatePolicyDraft(draft, taskClasses)`, and `policyPayload(draft)`; it is tested with Node's existing built-in test runner.

- [ ] **Step 1: Add a failing pure-form test for a changed ceiling preview and invalid rule handling**

```jsx
test('policy payload preserves a changed refund ceiling and every task class', () => {
  const draft = draftFromPolicy(policy)
  draft.rules.refund.l2_ceiling = '25'
  assert.deepEqual(validatePolicyDraft(draft, taskClasses), [])
  assert.equal(policyPayload(draft).rules.find((rule) => rule.task_class === 'refund').l2_ceiling, 25)
})
```

- [ ] **Step 2: Run the form test and verify the new module is absent**

Run: `npm --prefix frontend test -- test/policyForm.test.js`

- [ ] **Step 3: Implement the policy editor and impact confirmation flow**

Present existing policy version, task-class rules, sample/pass-rate requirements, preview outcome, and a single explicit activate control. Copy must state that policy changes affect future runs and do not silently grant more autonomy.

- [ ] **Step 4: Add policy version/evaluation context to Overview**

Show active policy version and each class's evidence progress without displacing the existing license/detection state.

- [ ] **Step 5: Run frontend test/build checks**

Run: `npm --prefix frontend test`

Run: `npm --prefix frontend run build`

- [ ] **Step 6: Commit the UI slice**

```bash
git add frontend/src/lib/api.js frontend/src/features/app/components/PolicyEditor.jsx frontend/src/features/app/components/policy-editor.css frontend/src/features/app/components/policyForm.js frontend/src/features/app/pages/Settings.jsx frontend/src/features/app/pages/Overview.jsx frontend/test/policyForm.test.js
git commit -m "feat: add policy review and activation UI"
```

### Task 7: Full verification, migration exercise, and documentation

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Create: `docs/policy-governance.md`
- Test: `tests/test_policy_service.py`

**Interfaces:**
- Documents policy lifecycle and Anthropic/neatlogs secret ownership without changing their public API.

- [ ] **Step 1: Write a migration smoke test using a pre-policy database and a real startup rebuild**

```python
def test_existing_demo_database_boots_with_a_v1_policy(tmp_path):
    # create legacy schema/data, then build_app
    assert context.policy_service.active().version == 1
    assert context.worker.run_refund(...).run_id
```

- [ ] **Step 2: Run the migration smoke test and full backend suite**

Run: `.venv/bin/python -m pytest`

Expected: all tests pass.

- [ ] **Step 3: Run the production frontend build**

Run: `npm --prefix frontend run build`

Expected: build succeeds.

- [ ] **Step 4: Document normal-user policy operations and configuration ownership**

Explain Anthropic setup, optional neatlogs settings, active policy review, impact confirmation, evidence needed for promotion, and safe recovery when a task class is paused.

- [ ] **Step 5: Commit verification and documentation**

```bash
git add README.md .env.example docs/policy-governance.md tests/test_policy_service.py
git commit -m "docs: explain policy-governed autonomy"
```
