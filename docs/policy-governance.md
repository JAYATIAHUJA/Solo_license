# Operating Solo License policies

Solo License is a control system for an agent that can take customer-facing
actions. The model may read a request and propose a plan, but it does not
choose its own permissions. The active policy, the task-class license level,
and a server-issued one-time permit must all agree before a refund or store
credit can be written.

## Normal workspace setup

1. Start the app and sign in with an **admin** access token supplied by the
   person who deployed the workspace. The token identifies the actor in the
   audit trail; it is not an Anthropic, neatlogs, or GitHub token.
2. Complete onboarding with a business name and starting autonomy level for
   each task class.
3. In **Settings → AI model**, choose **Anthropic**, enter an Anthropic API
   key, and use the model name enabled for that account. Test the connection
   before saving. The model is used only for intake and planning.
4. Optionally add a neatlogs API key and project in **Settings → Activity
   recording**. Test it, then save. Remote neatlogs traces make every run easy
   to inspect; the product remains functional without one because local spans
   and evidence are kept in the workspace database.
5. Open **Home** to see the active policy version and the evidence needed for
   each task class to earn its next autonomy level.

The normal setup screen stores user-entered API keys encrypted at rest. It
shows only a masked hint after saving, never the full secret.

## Who owns each secret

| Value | Where it belongs | When it is needed |
| --- | --- | --- |
| Anthropic API key | Workspace Settings, or `ANTHROPIC_API_KEY` as a deployment fallback | Needed only for model-authored intake and plans. Without it, deterministic intake/planning still works. |
| neatlogs API key | Workspace Settings, or `NEATLOGS_API_KEY` as a deployment fallback | Optional for remote trace viewing. Do not require it merely to run the agent. |
| `SOLO_API_TOKENS` | Deployment environment only | Required outside demo mode. These are access tokens for people using the workspace. |
| `SOLO_SETTINGS_ENCRYPTION_KEY` | Deployment environment only | Required in production before Settings can save any secret. Generate it once and keep it stable. |

Saved workspace settings take precedence over their deployment fallback. This
lets a hosted installation serve separate customer workspaces without exposing
the deployer's own provider key to the browser.

## Reviewing and changing autonomy

Only an admin can activate a policy. In **Settings → Policy review**:

1. Read the currently active version and its rules.
2. Give the proposed version a clear name and summary.
3. Set the lowest license level that may act without approval, the L2 ceiling,
   evaluation-window size, minimum clean samples, and minimum verified pass
   rate for every registered task class.
4. Select **Preview impact**. Solo License calculates the effect before any
   change is written. By default, a new version holds the current autonomy
   level safely; it never silently promotes a task class.
5. Read the impact for every class and select **Activate this policy version**
   only when it is intended.

Activation creates a new immutable version. Old rules and the version recorded
on old runs are retained. The agent must collect the new policy's evidence
before it can earn another promotion. The Home screen makes the current
sample count and verified pass rate visible.

## What happens during a customer action

1. Intake turns the message into a proposed refund or store-credit request.
2. The license level and active policy decide whether it can execute, needs
   approval, or must only be suggested.
3. Immediately before a write, the server mints a short-lived permit bound to
   the task class, allowed tool, exact order, exact amount, actor, and policy
   version.
4. The write function consumes that permit atomically. It cannot be reused,
   modified for another amount, or used after expiry.
5. The verifier reads the database back. A clean result becomes evidence for
   that policy version; a detected problem pauses the affected task class.

This is why the system can demonstrate a policy violation safely: the attempt
is logged and causes a demotion, but the unauthorized write is blocked before
customer data changes.

## When a task class is paused

A paused class behaves as L0: it can suggest, but it cannot act alone. Open
the corresponding evidence packet, inspect the before/after values and trace,
then have an approver restore it to a deliberate level. Do not retry blindly.
The restore is recorded in the audit ledger; clean runs then begin collecting
evidence again under the current policy.

## Deployment checklist

- Set `SOLO_DEMO_MODE=0`.
- Set `SOLO_API_TOKENS` with separate operator, approver, and admin tokens.
- Set one persistent `SOLO_SETTINGS_ENCRYPTION_KEY`.
- Set `SOLO_ALLOWED_ORIGINS` to the production frontend URL.
- Use persistent storage for `SOLO_LICENSE_DB` and a writable Git repository
  for `SOLO_LEDGER_REPO`.
- Configure `NEATLOGS_API_KEY` only when the deployment owner is intentionally
  providing a shared trace project. Otherwise, let the workspace admin add
  their own key in Settings.
- Confirm the Anthropic test and neatlogs test from Settings using non-demo
  credentials before inviting operators.
