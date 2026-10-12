# Policy Governance Foundation Design

## Purpose

Solo License must make every autonomous action demonstrably safe before it is
executed. A workspace owner configures a versioned policy; the agent may plan
work, but the server alone issues a short-lived, single-use permit for an
allowed tool call. An independent verifier then records the actual side effect.
Promotion and demotion are measured against the policy version that governed
the run.

This is the first deliverable in the wider PRD-completion program. It covers
F1, F3, F5, and F14. The later workflow/recovery, evaluation/export,
sponsor-evidence, and deployment milestones depend on these records.

## Success criteria

- A policy version explicitly describes per-task-class tools, approval mode,
  L2 ceiling, promotion window, sample size, and required verified pass rate.
- Editing a policy creates a new immutable version; existing runs retain the
  version that governed them.
- A database write cannot occur without a validated execution permit that
  matches the policy, task class, order, amount, and intended tool.
- The existing `policy_violation` fault demonstrates a blocked write, rather
  than a write that is merely detected after the fact.
- Promotions use the current policy's scoped evaluation window and pass-rate
  requirement. Any verified failure demotes/quarantines immediately.
- Changing policy produces an impact record showing the new conditions and
  which currently earned autonomy states no longer qualify.
- The current refund and store-credit demos remain runnable with a generated
  default policy migrated from existing settings.

## Data model

`policies` is an immutable policy header:

- `id` integer primary key
- `version` integer, unique and monotonically increasing per workspace
- `name`, `status` (`active` or `superseded`), `created_by`, `created_at`
- `summary` human-readable rationale

`policy_rules` belongs to one policy version and one task class:

- `task_class`, `allowed_tool` (`refund` or `store_credit`)
- `requires_approval_at_or_above` integer level
- `l2_ceiling` positive decimal
- `evaluation_window` positive integer
- `minimum_samples` positive integer
- `minimum_verified_pass_rate` decimal in `[0, 1]`

`execution_permits` records a server-issued, single-use authorization:

- opaque random token digest only, never the raw token
- policy version/rule identity, task class, tool, order, amount
- run candidate/id, actor, issued/expiry/consumed timestamps, and disposition

`policy_impacts` records policy-change consequences:

- old/new policy versions, task class, prior and recalculated qualification,
  required evidence versus available evidence, and explanatory reason.

The database bootstrap/migration creates a default `v1` from the existing
refund/store-credit settings when no policy exists. Existing `runs` gain
`policy_version`; historical rows are assigned to the initial policy. This
preserves the current demo and makes the migration idempotent.

## Server-side authorization boundary

The worker still plans first, but it cannot call a side-effecting adapter with
only a `Decision`. It asks a `PolicyGate` for an `ExecutionPermit` after the
current policy, license state, user approval, and amount have been checked.

The tool adapter accepts a permit, not a raw authorization enum. Immediately
before its database mutation it validates all permit fields, expiry, state,
and single-use status transactionally. A mismatch returns a blocked result and
does not mutate `orders`. The permit is then atomically consumed with the
write. A test-only fault may request an unauthorized action, but it receives a
blocked result and yields an auditable `policy_breach` detection; it must never
be able to bypass the gate.

The existing post-execution read-back verifier remains mandatory. The permit
adds prevention; it does not replace verification.

## Policy evaluation and autonomy

For each task class, promotion examines the most recent verified executions
under the currently active policy version. A promotion is permitted only when:

1. at least `minimum_samples` runs are available within `evaluation_window`;
2. the verified-clean ratio meets `minimum_verified_pass_rate`; and
3. the task class is not quarantined.

The policy's approval and ceiling rules govern whether a run is eligible to
execute; the existing license level still determines the autonomy level. A
single detection remains an immediate quarantine/demotion, independent of
aggregate pass rate. Runs under older policies remain evidence for their own
audit history but do not satisfy a newly changed policy by default.

On policy activation, the server recalculates each task class against the new
version and writes policy-impact records. It never silently raises autonomy.
If new requirements are not met, the state is held at its current safe level
and the dashboard explains what evidence is missing. Explicitly stricter rules
may pause a class only when the operator elects that policy option; the default
is hold/review rather than automatic destructive demotion.

## API and user experience

New admin-only policy endpoints will support listing versions, previewing a
draft impact, activating a validated policy, and reading impact records. The
dashboard payload will include the active policy, the rule governing each task
class, evaluation progress, and policy version on each run.

The settings surface will receive a focused **Autonomy policy** section. It
uses plain language: allowed action, human-approval boundary, L2 ceiling,
evidence sample, evaluation window, and required pass rate. Activation shows
a confirmation page with impact before it writes a new version. The initial
defaults reproduce the present safe demo behavior: refund ceiling $50,
store-credit ceiling $75, three-sample window, three minimum samples, and a
100% verified-clean requirement.

## Anthropic and observability configuration

The Anthropic key is configured through the encrypted Settings/onboarding
secret field or through `ANTHROPIC_API_KEY` in deployment environment. Select
`LLM_PROVIDER=anthropic`; `ANTHROPIC_MODEL` contains the exact model identifier
supported by that account. The connection test makes a tiny real planning call.
LLM output remains untrusted planning input and cannot create a permit.

`NEATLOGS_API_KEY` is optional for product operation. When absent, Solo License
uses its local span mirror and evidence remains functional. It is appropriate
as a deployment environment variable when the operator owns one shared
neatlogs workspace. If each customer supplies their own neatlogs account, the
key must instead be saved through the encrypted workspace settings UI; it must
not be placed in frontend configuration. The later sponsor-evidence milestone
will run the Doctor probe in an isolated process so it cannot collide with the
live tracer.

## Testing and safety constraints

- Test first: a policy-violation attempt must leave the order balance unchanged.
- Test immutability, migration/reseed behavior, policy impact computation,
  permit expiry/single-use/mismatch rejection, and scoped evaluation results.
- Preserve existing idempotency and independent-verification tests.
- No raw secret appears in a response, trace attribute, subprocess argument,
  source file, or test snapshot.
- All schema migrations are idempotent for an existing SQLite database.

## Out of scope for this deliverable

- Additional agent task classes, multi-step tool loops, recovery receipts,
  review queues/kill switches, downloadable report generation, cfo.ai exports,
  Entire execution evidence, Docker/Postgres deployment, and front-end
  presentation polish. These are subsequent PRD milestones built on this
  policy foundation.
