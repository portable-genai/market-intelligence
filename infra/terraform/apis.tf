# apis.tf : Enable exactly the managed services market-intelligence depends on.
#
# Control map:
#   Managed-first / minimal surface (SPEC 3): only the services the pinned gcp adapter stack
#         actually uses are enabled. Nothing speculative. The gcp adapters bound in
#         config/settings.yaml are: deep_research + gemini_llm + genai_eval (aiplatform),
#         file_search_kb (discoveryengine, via the GenAI File Search store),
#         model_armor_guardrail (modelarmor), cloud_logging_audit (logging),
#         cloud_trace_tracer (cloudtrace), a2a_registry + mcp_tool_catalog (aiplatform).
#         There is NO BigQuery, Document AI, DLP, Cloud Storage or AlloyDB adapter in this
#         repo, so those APIs are intentionally absent.
#   Residency (SPEC 2): enabling these APIs is a prerequisite for the regional,
#         CMEK-protected resources defined in the sibling files.
#
# disable_on_destroy = false so a `terraform destroy` of this stack does not yank platform
# APIs out from under other workloads in a shared project.

locals {
  required_services = [
    # --- Services backing a bound gcp adapter (SPEC 3 port table) ---
    "aiplatform.googleapis.com",      # Gemini reasoning + Deep Research + Gen AI eval + A2A/MCP
    "discoveryengine.googleapis.com", # File Search / Agent Search over the internal corpus
    "modelarmor.googleapis.com",      # Model Armor guardrail (input/output screening)
    "logging.googleapis.com",         # Cloud Logging (WORM locked bucket + audit sink)
    "cloudtrace.googleapis.com",      # Cloud Trace (OpenTelemetry spans)
    # --- Serving + residency/CMEK/perimeter infrastructure ---
    "run.googleapis.com",                  # Cloud Run v2 API service host (port 8100)
    "artifactregistry.googleapis.com",     # Container image registry (asia-southeast1)
    "cloudkms.googleapis.com",             # Regional CMEK key ring (CMEK does not cascade)
    "orgpolicy.googleapis.com",            # Org Policy residency constraints (SPEC 2)
    "accesscontextmanager.googleapis.com", # VPC Service Controls perimeter (SPEC 2)
    "monitoring.googleapis.com",           # Log-based metrics + posture alert policies
    # --- Supporting services the above transitively require ---
    "compute.googleapis.com", # VPC / networking for the perimeter
    "iam.googleapis.com",     # Service accounts / least-privilege IAM
  ]
}

resource "google_project_service" "required" {
  for_each = toset(local.required_services)

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
