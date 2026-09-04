# iam.tf : Least-privilege runtime service account for the market-intelligence Cloud Run service.
#
# Control map:
#   Least privilege (SPEC 3): a single dedicated runtime identity for the serving / API
#         workload, granted only the roles its bound gcp adapters need : call Gemini /
#         Deep Research / eval and File Search (aiplatform.user covers Discovery Engine
#         retrieval and Vertex reasoning), screen with Model Armor, write audit events to
#         the WORM sink, and emit trace spans. No broad / kitchen-sink role.
#   No service-account keys: the identity is used via Workload Identity (Cloud Run sets it as
#         the service identity); no exported key is created here (org_policy.tf forbids it).
#   CMEK explicit: the runtime SA gets its own cryptoKey-use binding for envelope ops.

resource "google_service_account" "runtime" {
  account_id   = "mkt-market-intel-run"
  display_name = "market-intelligence Market Intelligence : Cloud Run runtime (serving / API)"
  project      = var.project_id

  depends_on = [google_project_service.required]
}

locals {
  # Serving path: external Deep Research + Gemini + eval + File Search retrieval, Model Armor
  # screening, audit write, trace spans. Read-only against managed sources; no write to them.
  runtime_roles = [
    "roles/aiplatform.user",         # Gemini reasoning + Deep Research + Gen AI eval + A2A/MCP
    "roles/discoveryengine.viewer",  # query the File Search / Agent Search corpus
    "roles/modelarmor.user",         # input/output guardrail screening
    "roles/logging.logWriter",       # write audit events to the WORM sink
    "roles/cloudtrace.agent",        # OpenTelemetry spans (content OFF)
    "roles/monitoring.metricWriter", # emit service metrics
  ]
}

resource "google_project_iam_member" "runtime" {
  for_each = toset(local.runtime_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.runtime.email}"
}

# Runtime uses the CMEK for envelope ops it performs directly.
resource "google_kms_crypto_key_iam_member" "runtime" {
  crypto_key_id = google_kms_crypto_key.mkt.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.runtime.email}"
}
