# Runbook: `market-intelligence` Market Intelligence and Competitor Analysis

Operational notes for deploying and running `market-intelligence` on the Gemini Enterprise Agent Platform in a
residency region (defaults `asia-southeast1`; JP and AU are per-market overrides). This is a
reference build; adapt it to your own change-management and model-risk sign-off before any
live use.

## 0. Profiles

`MKT_INTEL_PROFILE` selects the adapter stack. It has **no default**: an unset (or blank)
variable is treated as "no profile was chosen", which binds the SDK-free adapters so the
process still boots but grants none of the local relaxations. The seeded dev personas are
refused (every end-user route answers 401), the CORS dev origins are withheld, and the bind
guard still confines the process to loopback. Name the profile deliberately. An unknown or
mis-capitalised value (`Local`, `GCP`) is refused outright rather than silently selecting
neither the relaxations nor the restrictions.

- `local` (SDK-free): the whole pipeline runs offline (SQLite FTS5 corpus,
  deterministic deep-research synthesiser and LLM). No Google Cloud SDK. This is what CI and
  the demo run.
- `gcp`: the managed stack (Gemini with Google Search grounding, File Search, Model Armor,
  Cloud Logging).
- `platform`: consume the shared Hrz services (KB / guardrail / audit / eval / registry) over
  S2S instead of standalone GCP clients.
- `onprem`: fail-fast placeholders that raise `NotImplementedError`, the migration target
  (see `docs/onprem-migration.md`).

`MKT_VERTICAL` (`banking` | `online_retail`) and `MKT_MARKET` (`JP` | `AU` | `SG`) select the
active vertical and market; the market's residency region and locales come from the per-market
profile in `config/settings.yaml`, never a hard-coded branch.

## 1. Offline demo and smoke (no cloud)

```bash
make demo          # build a cited brief + render the static audit-first HTML into scripts/out
make smoke-local   # end-to-end offline: build one cited brief under the local profile
make run-api       # FastAPI on 127.0.0.1:8100 (local profile binds loopback by default)
```

The agent card is served at `GET /.well-known/agent-card.json` and the health probe at
`GET /healthz` (reports the active profile, market and vertical).

## 2. Deploy (managed stack)

```bash
# 1. Provision infra (review the plan; the WORM bucket lock is irreversible when
#    worm_locked = true; it has no default, so state it).
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # set project_id, org_id, access_policy_id
terraform init -input=false && terraform plan
terraform apply

# 2. Export the outputs the app reads.
export GOOGLE_CLOUD_PROJECT="$(terraform output -raw project_id)"
export MKT_INTEL_REGION="$(terraform output -raw region)"
export MKT_INTEL_KMS_KEY="$(terraform output -raw kms_key)"
export MKT_INTEL_LOG_BUCKET="$(terraform output -raw log_bucket)"

# 3. Install the managed stack and run the API. With review routing on (the default) the
#    process refuses to boot without the console it routes to.
pip install -e ".[gcp,dev]"
export GOOGLE_CLOUD_PROJECT=your-sg-project MKT_INTEL_PROFILE=gcp
export HUMAN_REVIEW_URL=https://human-review.your-bank.example   # or MKT_INTEL_REVIEW_ROUTING=off
gcloud auth application-default login
make run-api PROFILE=gcp          # FastAPI on :8100 (front with the platform ingress)
```

For a quick project-scoped evaluation WITHOUT org-level prerequisites, set `enable_vpc_sc =
false` and `worm_locked = false` so everything stays deletable (not
compliant for production). See `infra/terraform/terraform.tfvars.example` and
`infra/terraform/README.md`.

The ADK agent is deployed to Agent Runtime separately via the Agent Platform SDK; see the
docstring in `src/market_intelligence/agent/root_agent.py`. Record the resulting
`reasoningEngine` resource name in `settings.agent_engine.resource_name` (or
`MKT_AGENT_ENGINE`). To attach an out-of-process governed MCP tool server, set
`MKT_INTEL_MCP_SERVER_URL`; unset, the agent uses its in-process FunctionTools.

## 3. Region selection and fail-fast

The Terraform `region` is validated against the residency allowlist; an apply against a region
outside it fails at `terraform plan`, before anything is created. Model Armor, Cloud Logging
and the WORM bucket are all created in the selected region, and a `gcp.resourceLocations` Org
Policy hard-restricts resource creation to it. The app also validates the active market's
region at load via `config.market_profile()`, so a mismatched deploy fails fast on both sides.

## 4. Key rotation, retention and the WORM lock

The CMEK crypto key (`kms.tf`) rotates on schedule; rotation is transparent to the app. The
audit bucket retention is `retention_days` (default 2557, ~7 years) and the bucket is
locked by `worm_locked = true` (no default), which is **irreversible**. To trial without locking, set `worm_locked = false` (not compliant for production). Only screened prompts and
responses are ever written to the audit log.

## 5. Kill switch

To stop serving without tearing down state: scale the Cloud Run / Agent Runtime deployment to
zero, or remove the app service account's `roles/aiplatform.user` binding. The audit trail and
the corpus index remain intact.

## 5a. Runtime controls

`MKT_INTEL_GUARDRAIL` and `MKT_INTEL_REVIEW_ROUTING` each switch one cheap runtime
control, read once at startup in three states: unset is on, `true`/`false` (or `on`/`off`,
`1`/`0`, `yes`/`no`) wins, and an emptied or unrecognised value refuses to boot, naming the
variable. The Terraform states both (`guardrail_enabled`, `review_routing_enabled`, default
`true`). This service has no PII redaction port, so it has no redaction switch.

- **Guardrail off** binds a guardrail that allows everything unchanged. Under `gcp` with the
  guardrail on, an empty `model_armor.template_id` refuses to boot rather than building a
  malformed Model Armor URL at the first request.
- **Review routing off** binds a router that submits nothing. Every brief is still audited
  `ESCALATED` and still says `requires_human_review`, and every response reports
  `review_routing: "off"` so nobody reads it as queued for a reviewer. Under `gcp` or
  `platform` with routing on, an unset `HUMAN_REVIEW_URL` refuses to boot; set the switch off
  to run without a console, rather than leaving the URL out.
- A process with either control off logs one `WARNING` at startup naming each.

Every caller that hands a brief to the review console reports what happened to it:
the API response and the agent tool's payload carry `review_routing`, the MCP
`deep_research` tool returns it with the brief, and the CLI `brief` command prints it (`routed`, `failed`, `off`, `not_required`). A hand-off that fails is logged at
`WARNING` with the exception type and reported as `failed`; the brief itself is still
returned, and the console says it is not queued for review.

## 6. Common failures

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `NotImplementedError` from a CLI command (exit 2) | `MKT_INTEL_PROFILE=onprem` with placeholder adapters | Set `MKT_INTEL_PROFILE=gcp` (or implement the on-prem adapter) |
| Boot refused: "Review routing is on ... but HUMAN_REVIEW_URL is not set" | `gcp`/`platform` with routing on and no console named | Set `HUMAN_REVIEW_URL` (Terraform `human_review_url`), or state `MKT_INTEL_REVIEW_ROUTING=off` |
| A response says `review_routing: "failed"` | The review console was unreachable or refused the hand-off; the log names the exception type | Restore the console; the brief is not queued, so resubmit it once the console answers |
| `ResearchEmptyError` on a brief (HTTP 404) | Deep research and the corpus both returned nothing after dedup | Broaden the topic, confirm grounding is enabled, or seed the internal corpus |
| Guardrail block on a benign brief (HTTP 400) | Model Armor template too strict | Tune the `model_armor` template filter confidence levels |
| CORS error from the embedded UI | Origin not in the per-tenant allowlist | Add the parent origin to `MKT_INTEL_CORS_ORIGINS` (never `*`) |
| VPC-SC denies the apply | Runner identity outside the perimeter | Apply with `vpc_sc_enforce = false`, add the identity to `operator_members`, re-apply true |
