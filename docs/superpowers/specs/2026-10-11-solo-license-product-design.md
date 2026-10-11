# Solo License product-ready demo design

## Purpose and success criteria

Solo License must demonstrate a trustworthy refund agent, not merely a chat
screen. A first-time evaluator must be able to enter a demo workspace, complete
onboarding, run a safe refund, inject a fault, see automatic demotion and human
recovery, and inspect an evidence packet. A prospective customer must be able to
configure their own model provider and observability credentials without exposing
secrets back to the browser.

The implementation remains runnable with no paid key, hosted database, or cloud
account. It uses the existing SQLite store for the single-machine demo only and
keeps explicit seams for a later hosted authentication and database layer.

## Product scope

### Access and onboarding

The client will have a clear **Try the demo** path and a **Connect an existing
workspace** path. Try the demo obtains a local-only demo session from the API;
it is never enabled in a production deployment. Existing-workspace access accepts
a deployment-issued access token and stores it only in browser session storage.

After access is established, onboarding collects workspace name, model provider,
model connection test, safety rules, and demo/sample orders. The UI will clearly
label deterministic mode as the no-key choice. It will not claim to create a
multi-user account: true sign-up/sign-in is deferred until hosted authentication
is configured.

### Model providers and secret handling

The supported provider choices are:

1. Deterministic demo mode (no key).
2. Google Gemini using a Gemini API key and configurable model.
3. Anthropic.
4. OpenAI.
5. GLM or another OpenAI-compatible endpoint, with key, model, and HTTPS base
   URL supplied by the customer.

Provider fields have one canonical metadata table in the frontend and matching
allow-listed settings in the backend. API keys are posted only to the API, saved
through the existing encryption mechanism, masked on every read, and never sent
to logs or evidence packets. Connection tests make a minimal request and return
only a bounded status message.

### Safety and evidence

The existing licensed refund worker remains the source of truth: it enforces
levels, idempotency, refund ceilings, verification, fault injection, automatic
demotion, human approval, and evidence packets. neatlogs remains optional; when
configured, it records the workflow trace and the UI states whether remote
observability is active. The evidence view will remain usable with no neatlogs
key.

`cfo.ai` and Entire are hackathon/developer integrations, not customer API-key
fields. The app will include an honest finance-review export/readout; cfo.ai can
analyse that material through its OAuth MCP workspace once the team connects it.
Entire is configured for code checkpoints and Graph. Trails waits for Entire's
account-level feature flag and repository-admin toggles.

## Architecture and interfaces

### Backend

`Config` gains Gemini and OpenAI-compatible provider settings. A provider
resolver in the LLM intake module dispatches the current Anthropic/OpenAI calls,
Gemini REST call, or OpenAI-compatible REST call. The resolver has a single
`complete(config, prompt, max_tokens)` interface so intake and planner do not
need provider-specific code.

The API expands its setting allowlist, secret masking, serialization, validation,
and connection-test construction. The demo-session endpoint is isolated from
role-protected endpoints and enabled only by an explicit local-demo environment
flag. It returns a short-lived configured demo token; no implicit unauthenticated
fallback is permitted.

### Frontend

The API wrapper reads a session token from a small access-session module and
adds a Bearer header. The access screen is shown before onboarding or app routes
when no token is present. The onboarding and Settings model form consume shared
provider metadata so every provider exposes the right fields, placeholders, and
masked-key hints. The route guard sends an un-onboarded workspace to onboarding
and an onboarded workspace to the dashboard.

### Future hosted deployment seam

The browser depends only on a token provider, and the API depends only on an
authenticated `Actor`. A future hosted auth provider replaces the demo/token
access flow without changing worker code. SQLite repositories remain behind their
current service boundaries so PostgreSQL/Supabase can replace them later. No
schema migration or cloud deployment is in this delivery.

## Error handling and security

- Reject unsupported provider identifiers, blank required fields, and non-HTTPS
  custom endpoints before a request is made.
- Treat failed model tests as recoverable configuration errors; never overwrite a
  saved key because a masked or blank field was submitted.
- Use timeouts and response-size/error-message bounds on network providers.
- Never ship a demo session endpoint with the demo mode flag enabled in a hosted
  deployment.
- Continue to require server-side encryption for persisted secrets.

## Verification

Tests will cover provider dispatch/config validation, provider secret masking,
demo-session access boundaries, browser authorization header behavior, and the
onboarding/provider-field flow. Existing refund state-machine, API-security, and
secret-storage tests remain green. The frontend production build must pass.

## External prerequisites that cannot be manufactured in code

- A Gemini API key is required only for live Gemini calls; deterministic mode
  keeps the demo runnable without one.
- A GLM/OpenAI-compatible key, model name, and HTTPS base URL are required only
  for that provider.
- A neatlogs ingest key enables remote traces; it is optional for the demo.
- cfo.ai uses an authenticated OAuth MCP connection, not a customer-facing API
  key field.
- Entire Trails requires the team to obtain the feature flag, then an admin to
  enable Runners, Auto build on push, and Trails for the GitHub repository.
