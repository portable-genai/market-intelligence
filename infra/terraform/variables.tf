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

variable "model_armor_full_capabilities" {
  type        = bool
  default     = true
  description = <<-EOT
    Whether the guardrail template asks for the capabilities that are not served in every
    region: the malicious-URI filter and multi-language detection.

    True by default, because a deployment should get the whole guardrail unless it has a reason
    not to. asia-southeast1 serves neither, and Model Armor does not degrade: it refuses the
    template with CAPABILITY_NOT_SUPPORTED, so the stack does not deploy at all. A deployment
    there sets this false, which narrows the guardrail and is a disclosure to make in the
    deployment's posture record rather than a silent downgrade. JP (asia-northeast1) and AU
    (australia-southeast1) deploys of this stack's per-market variant confirm capability support
    for their own region before leaving this at the default.
  EOT
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

variable "worm_locked" {
  description = <<-EOT
    Lock the WORM audit bucket. WARNING: LOCKING IS IRREVERSIBLE. With true, the bucket and its
    retention window can NEVER be reduced or deleted until every entry ages out, not even with
    project-owner rights. true is the compliant production form; false keeps the stack
    destroyable and is NOT compliant.

    There is deliberately NO DEFAULT. A plan refuses until the deployment names the lock,
    because an unset value may take a reviewed default and may never take an irreversible one.
    This stack used to hard-code the lock, so its first apply anywhere locked the bucket for the
    whole retention window with no way for a deployment to decline. Every stack that has this
    control spells it `worm_locked`, and none of them defaults it.
  EOT
  type        = bool
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

variable "resource_location_values" {
  description = <<-EOT
    Value groups for the gcp.resourceLocations Org Policy. Empty (the default) derives the
    strictest form from the deploy region: that region and its sub-locations, nothing else.

    Widen it ONLY where a service this stack genuinely needs has no presence at single-region
    granularity, and treat the width as the residency claim rather than as plumbing. Two
    services in this catalog force the question:

      * Agent Search serves `global`, `us` and `eu` and NO Cloud region at all.
      * Document AI serves the deploy region only once Google grants single-region access,
        and routes to the `us` multi-region until then.

    Move to the smallest value group that still describes ONE JURISDICTION -- `in:us-locations`
    keeps every resource inside the United States -- and state the residency claim at that
    granularity rather than pretending it is still single-region. NEVER list an individual
    foreign region to unblock one service: that turns a jurisdiction boundary into a list of
    exceptions nobody can reason about.

    NOT YET VERIFIED BY EXECUTION: whether a `global` Agent Search data store is subject to
    this constraint at all, or is exempt as a global resource. Confirm at first apply and
    record the answer rather than guessing; the failure mode if it IS subject is an apply
    error naming discoveryengine, which is the good kind of failure.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for value in var.resource_location_values : startswith(value, "in:") || startswith(value, "is:")])
    error_message = "Each value must be an Org Policy location value group (in:...) or a literal location (is:...)."
  }
}

variable "manage_audit_config" {
  type        = bool
  default     = false
  description = <<-EOT
    Whether THIS stack writes the project's data-access audit configuration.

    False by default, and the default is the point. `google_project_iam_audit_config` is
    AUTHORITATIVE for the service it names, so a second stack declaring `allServices` does
    not add to that configuration, it REPLACES it, and a stack asking for DATA_READ and
    DATA_WRITE removes an ADMIN_READ a sibling enabled. Terraform reports that as a create
    rather than a change, because this stack holds no prior state for a resource that is
    nonetheless already live. Nearly every stack in this fleet carries this resource and one
    project hosts many of them, so a default of true is a race whose winner is whichever
    stack applied last.

    Data-access logs are also the highest-volume class Cloud Logging ingests, and nothing in
    the reference deployment reads them.

    Set true in exactly one stack per project, in that deployment's own tfvars, where the
    project genuinely wants data-access logging on.
  EOT
}

variable "posture_alerts_enabled" {
  type        = bool
  default     = false
  description = <<-EOT
    Whether this stack creates the posture alert policies and the log-based metrics behind
    them. False by default. Cloud Monitoring bills every metric-based alert condition, and a
    reference deployment that nobody pages gains nothing from them: the signals still land in
    Cloud Logging, where an operator can read them. Set true in a deployment with an on-call
    rota to notify, in that deployment's own tfvars.
  EOT
}

variable "cmek_enabled" {
  type        = bool
  default     = false
  description = <<-EOT
    Whether this stack creates its own Cloud KMS key ring and key and binds every store, log
    bucket and revision to it. False by default, and the default is the point: a key ring can
    never be deleted, a log bucket that has CMEK can never drop it, and registries and document
    stores take their key at creation. None of that changes an answer or a screen, and every
    resource is encrypted at rest with Google-managed keys regardless. A deployment with a
    customer whose data it must be able to shred, whose key access must be audited, or whose
    keys must live in an HSM sets this true in its own tfvars BEFORE its first apply. Flipping
    it off on a stack that already applied it is refused by the keys' prevent_destroy, which is
    the right answer: the stores it bound stay bound.
  EOT
}

# --------------------------------------------------------------------------- #
# Cheap runtime controls (the fleet's runtime-control contract). Each is on in the reference,
# reversible, and therefore takes a default; off is a stated deployment choice the service logs
# at startup.
# --------------------------------------------------------------------------- #
variable "guardrail_enabled" {
  description = "Switch the input and output guardrail (Model Armor under gcp) on the service (MKT_INTEL_GUARDRAIL). A cheap runtime control: on in the reference, reversible, so it takes a default."
  type        = bool
  default     = true
}

variable "review_routing_enabled" {
  description = "Switch the hand-off of every brief to the human-review-console (MKT_INTEL_REVIEW_ROUTING). A cheap runtime control: on in the reference, reversible, so it takes a default."
  type        = bool
  default     = true
}

variable "human_review_url" {
  description = <<-EOT
    The human-review-console base URL the review router submits every brief to
    (HUMAN_REVIEW_URL, rule R8). No default: with review routing on, the service refuses to
    boot without one, so a deployment names it or states review_routing_enabled = false (and
    then may pass ""). HTTPS, because the payload carries the brief.
  EOT
  type        = string

  validation {
    condition     = !var.review_routing_enabled || can(regex("^https://", var.human_review_url))
    error_message = "review_routing_enabled requires human_review_url, an https:// URL: the service refuses to boot with routing on and no console named. Name one, or set review_routing_enabled = false."
  }

  validation {
    condition     = var.human_review_url == "" || can(regex("^https://", var.human_review_url))
    error_message = "human_review_url must be an https:// URL."
  }
}
