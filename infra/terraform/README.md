# infra/terraform : `market-intelligence` Market Intelligence sovereign deploy

Terraform that makes the `market-intelligence` cloud posture enforceable at deploy time, not merely documented.
A control that lives only in a document is not a control: residency, encryption, perimeter and
audit are pinned here so `terraform plan` fails when a deploy would violate them, and a
reviewer can read each control next to the resource it governs.

This stack defaults to the **asia-southeast1 (Singapore) resident** deployment of `market-intelligence`. The
application serves three APAC markets (JP, AU, SG), each with its own in-country residency
region; apply a separate stack per market, setting that market's `region` and
`allowed_regions`. The region is selected at deploy time and validated against
`var.allowed_regions` (default `["asia-southeast1"]`), and the application validates its own
per-market allowlist at settings load
(`src/market_intelligence/adapters/gcp/_region.py`), so a deploy fails fast both at `plan`
and at runtime if pointed off-allowlist.

## What gets created

| File | Purpose |
|---|---|
| `providers.tf` | google + google-beta providers, region wired from `var.region`, no global endpoint |
| `variables.tf` | `region` validated against `allowed_regions` (both default to `asia-southeast1`); per-tenant knobs only |
| `terraform.tfvars.example` | fictional in-country sample values |
| `apis.tf` | enables only the managed services `market-intelligence`'s gcp adapters use, plus core infra |
| `org_policy.tf` | `gcp.resourceLocations` allowlist, disable SA-key creation, no external IP, uniform bucket access |
| `kms.tf` | one regional CMEK key + a per-service IAM binding (CMEK does not cascade) |
| `vpc_sc.tf` | service perimeter, dry-run first (`vpc_sc_enforce = false`) |
| `logging_worm.tf` | locked WORM log bucket + sink + Data Access audit config |
| `monitoring.tf` | log-based alerts: guardrail blocks, SA-key creation, VPC-SC denials, CMEK changes |
| `iam.tf` | least-privilege Cloud Run runtime service account (Workload Identity, no keys) |
| `cloud_run.tf` | the FastAPI image as a Cloud Run v2 service (port 8100, CMEK, controlled ingress) |
| `outputs.tf` | values to export into the runtime environment after apply |

## Services enabled (tied to the bound gcp adapters)

`apis.tf` enables only what the `gcp` profile actually calls (`config/settings.yaml` `adapters:`):

- `aiplatform.googleapis.com` : Gemini reasoning, Deep Research, Gen AI eval, A2A / MCP catalog.
- `discoveryengine.googleapis.com` : File Search / Agent Search over the internal corpus.
- `modelarmor.googleapis.com` : Model Armor guardrail (input / output screening).
- `logging.googleapis.com` : Cloud Logging WORM bucket + audit sink.
- `cloudtrace.googleapis.com` : Cloud Trace (OpenTelemetry spans).

Plus serving and posture infra: `run`, `artifactregistry`, `cloudkms`, `orgpolicy`,
`accesscontextmanager`, `monitoring`, `compute`, `iam`. There is no BigQuery, Document AI,
DLP, Cloud Storage or AlloyDB adapter in this repo, so those APIs are intentionally absent.

## Deploy order

1. Build and push the image to Artifact Registry in `asia-southeast1`; set `container_image`.
2. `terraform init && terraform apply` with `vpc_sc_enforce = false` (dry-run perimeter).
3. Watch the `vpc_sc_denials` alert / dry-run logs; add operator and CI identities to
   `operator_members`.
4. Re-apply with `vpc_sc_enforce = true` to enforce the boundary.

## WARNING : irreversible locks

- `logging_worm.tf` sets `locked = true` on the audit bucket. This permanently prevents
  reducing retention or deleting the bucket for the full window (~7 years). Confirm
  `retention_days` before the first apply.
- The CMEK key has `prevent_destroy = true`. Destroying it would strand all encrypted data.

## Validate

```bash
make tf-plan                       # from the repo root: plan for the selected region
# or directly:
cd infra/terraform
terraform fmt -recursive
terraform init -backend=false && terraform validate
```

No secrets are stored here. Identities use Workload Identity; org policy forbids exportable
service-account keys.
