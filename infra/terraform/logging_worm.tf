# logging_worm.tf : WORM audit trail : locked Cloud Logging bucket + sink + audit config.
#
# Control map:
#   Immutable audit / WORM (SPEC 3 AuditSinkPort, SPEC 5 maker-checker): the audit log is
#         routed to a Cloud Logging bucket whose retention is var.retention_days (~7 years)
#         and whose `locked = true` makes it Write-Once-Read-Many. The gcp audit adapter
#         (cloud_logging_audit) writes the Decision.ESCALATED maker-checker records here.
#   Residency (SPEC 2): bucket location is var.region (the selected, allowlisted region).
#   CMEK explicit: the bucket is CMEK-encrypted (logging SA key binding in kms.tf).
#
# ############################################################################ #
# # WARNING : LOCKING IS IRREVERSIBLE.                                        # #
# # Setting `locked = true` below permanently prevents reducing retention or  # #
# # deleting this bucket for the full retention window. You CANNOT undo it,   # #
# # not even with project-owner rights. Confirm retention_days before apply.  # #
# # To trial without locking, set locked = false (NOT compliant for prod).    # #
# ############################################################################ #

resource "google_logging_project_bucket_config" "worm_audit" {
  project        = var.project_id
  location       = var.region                 # the selected region (SPEC 2)
  bucket_id      = "market-intelligence-worm" # matches settings.yaml logging.bucket
  description    = "WORM audit bucket for Mkt1 market intelligence (locked, ~7y retention)."
  retention_days = var.retention_days # 2557 (~7 years) by default

  # IRREVERSIBLE : see WARNING banner above. WORM compliance requires this true.
  locked = true

  # CMEK on the log bucket : explicit, does not cascade.
  cmek_settings {
    kms_key_name = google_kms_crypto_key.mkt.id
  }

  depends_on = [
    google_project_service.required,
    google_kms_crypto_key_iam_member.logging,
  ]
}

# Route the audit log stream into the locked WORM bucket.
resource "google_logging_project_sink" "audit_to_worm" {
  project     = var.project_id
  name        = "market-intelligence-audit-to-worm"
  description = "Routes the market-intelligence-audit log to the locked WORM bucket."

  destination = "logging.googleapis.com/${google_logging_project_bucket_config.worm_audit.id}"

  # Capture this app's audit log + all Cloud Audit Logs (admin/data access).
  filter = <<-EOT
    logName="projects/${var.project_id}/logs/market-intelligence-audit"
    OR logName:"cloudaudit.googleapis.com"
  EOT

  unique_writer_identity = true
}

# --------------------------------------------------------------------------- #
# Enable Data Access audit logs so every read of the research sources and the
# audit store itself is itself audited.
# --------------------------------------------------------------------------- #
resource "google_project_iam_audit_config" "data_access" {
  project = var.project_id
  service = "allServices"

  audit_log_config {
    log_type = "DATA_READ"
  }
  audit_log_config {
    log_type = "DATA_WRITE"
  }
  audit_log_config {
    log_type = "ADMIN_READ"
  }
}
