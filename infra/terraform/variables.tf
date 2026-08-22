# variables.tf : The only knobs. Everything else is a concrete in-region value.
#
# Control map:
#   Residency (SPEC 2): `region` is SELECTED AT DEPLOY TIME and validated against the
#         in-country residency allowlist `allowed_regions`, so a caller fails fast rather
#         than deploying to an unvetted region. Both default to asia-southeast1 (the SG
#         market), so the out-of-the-box posture is unchanged and deploying elsewhere means
#         setting BOTH variables. The application validates its own allowlist at settings
#         load (src/market_intelligence/adapters/gcp/_region.py), so it fails fast
#         off-region too.
#   Auditability / retention (SPEC 3 AuditSinkPort): `retention_days` is a variable (the
#         WORM bucket lock is irreversible, so retention must be deliberate).
#
# Per the build contract, ONLY project_id and a few genuinely per-tenant values (org /
# Access Context Manager ids, the VPC-SC toggles, the container image) are variables. All
# service identifiers, locations and template names are concrete (see settings.yaml).

variable "project_id" {
  description = "Target GCP project id (required). Single-tenant, in-country resident."
  type        = string
}

variable "allowed_regions" {
  description = <<-EOT
    Residency allowlist: the regions this stack may be deployed to. The region is chosen at
    deploy time (var.region) and validated against this list to FAIL FAST (SPEC 2), so an
    operator cannot accidentally deploy to an unvetted region. Extending this list is the
    deliberate residency review point: add a region only after confirming the full managed
    stack (Vertex AI, Model Armor, DLP, Cloud Run, Cloud KMS, Logging) and your residency
    obligations are satisfied there. Each market is applied as its own stack, so a JP deploy
    sets this to ["asia-northeast1"] and an AU deploy to ["australia-southeast1"].
  EOT
  type        = list(string)
  default     = ["asia-southeast1"] # Singapore : the SG market default

  validation {
    condition     = length(var.allowed_regions) > 0
    error_message = "allowed_regions must list at least one residency-approved region."
  }
}

variable "region" {
  description = <<-EOT
    Deployment region, SELECTED AT DEPLOY TIME. Defaults to asia-southeast1 (Singapore, the
    SG market) but is overridable. Validated against var.allowed_regions so an unapproved
    region fails fast at `terraform plan` rather than deploying data out of jurisdiction
    (SPEC 2).
  EOT
  type        = string
  default     = "asia-southeast1" # Singapore : the SG market default

  # The app's own allowlist mirrors MARKET_PROFILES (JP -> asia-northeast1,
  # AU -> australia-southeast1, SG -> asia-southeast1); a sibling stack is applied per market
  # with its own in-country region and its own allowed_regions.
  validation {
    # Cross-variable validation (Terraform >= 1.9). Fails at plan time = setup time.
    condition     = contains(var.allowed_regions, var.region)
    error_message = "region must be one of var.allowed_regions (residency allowlist). Add it there first if that region is approved for this workload (SPEC 2)."
  }
}

variable "zone" {
  description = "Default zone for zonal resources. Must lie inside the selected var.region."
  type        = string
  default     = "asia-southeast1-a"

  validation {
    condition     = startswith(var.zone, "${var.region}-")
    error_message = "zone must be a zone of the selected region (e.g. \"${var.region}-a\")."
  }
}

variable "retention_days" {
  description = "WORM audit-log retention in days. Default ~7 years. Lock is irreversible."
  type        = number
  default     = 2557 # ~7 years; mirrors config/settings.yaml logging.retention_days

  validation {
    condition     = var.retention_days >= 2557
    error_message = "Compliance retention must be at least 2557 days (~7 years) to match settings.yaml logging.retention_days."
  }
}

variable "org_id" {
  description = "Organization id : required for Org Policy and Access Context Manager (VPC-SC)."
  type        = string
}

variable "access_policy_id" {
  description = <<-EOT
    Existing Access Context Manager policy id (numeric, no prefix) for the org.
    Required when enable_vpc_sc = true; the service perimeter is created under it.
    Create once per org with:
      gcloud access-context-manager policies create \
        --organization=ORG_ID --title="sg-residency"
  EOT
  type        = string
  default     = ""
}

variable "enable_vpc_sc" {
  description = "Create the VPC Service Controls perimeter around the AI/data APIs (SPEC 2)."
  type        = bool
  default     = true
}

variable "vpc_sc_enforce" {
  description = "Enforce the perimeter (true) vs DRY-RUN/audit (false, default). Apply false first, watch dry-run denials, then flip to true."
  type        = bool
  default     = false
}

variable "operator_members" {
  description = "Operator / CI identities (members:...) allowed to reach restricted APIs from outside the enforced perimeter."
  type        = list(string)
  default     = []
}

variable "container_image" {
  description = "Fully-qualified API image for Cloud Run (Artifact Registry, asia-southeast1)."
  type        = string
  default     = "asia-southeast1-docker.pkg.dev/REPLACE_WITH_PROJECT/mkt/market-intelligence:0.1.0"
}

variable "alert_notification_channels" {
  description = "Monitoring notification channel ids for the posture alert policies. Empty still creates the policies (no destination)."
  type        = list(string)
  default     = []
}
