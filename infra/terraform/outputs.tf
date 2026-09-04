# outputs.tf : Values the app / operators need to wire settings.yaml after apply.
#
# These map onto config/settings.yaml / config.py fields so a deploy is just
# "apply, then export these into the runtime environment".

output "project_id" {
  description = "The deployment project id."
  value       = var.project_id
}

output "region" {
  description = "The region this stack deployed to (selected at deploy time from var.allowed_regions)."
  value       = var.region
}

# --------------------------------- KMS -------------------------------------- #
output "kms_key" {
  description = "Regional CMEK crypto key id (export as MKT_INTEL_KMS_KEY)."
  value       = google_kms_crypto_key.mkt.id
}

# ------------------------------- WORM logging ------------------------------- #
output "log_bucket" {
  description = "Locked WORM audit log bucket id (settings.yaml logging.bucket)."
  value       = google_logging_project_bucket_config.worm_audit.id
}

output "audit_sink_writer_identity" {
  description = "Sink writer identity (grant it bucket access if cross-project)."
  value       = google_logging_project_sink.audit_to_worm.writer_identity
}

# ------------------------------- Cloud Run ---------------------------------- #
output "service_url" {
  description = "Base URL of the market-intelligence Cloud Run API service."
  value       = google_cloud_run_v2_service.api.uri
}

output "service_name" {
  description = "Cloud Run service name."
  value       = google_cloud_run_v2_service.api.name
}

output "agent_card_url" {
  description = "A2A AgentCard discovery URL for the market-intelligence service."
  value       = "${google_cloud_run_v2_service.api.uri}/.well-known/agent-card.json"
}

# ----------------------------- Service account ------------------------------ #
output "runtime_service_account" {
  description = "Least-privilege runtime identity (Workload Identity) used by Cloud Run."
  value       = google_service_account.runtime.email
}

# --------------------------------- VPC-SC ----------------------------------- #
output "vpc_sc_perimeter" {
  description = "Service perimeter name (empty when enable_vpc_sc = false)."
  value       = var.enable_vpc_sc ? google_access_context_manager_service_perimeter.mkt[0].name : ""
}

output "vpc_sc_enforced" {
  description = "Whether the perimeter is enforced (true) or in dry-run/audit (false)."
  value       = var.enable_vpc_sc ? var.vpc_sc_enforce : false
}
