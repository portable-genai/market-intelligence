# vpc_sc.tf : VPC Service Controls perimeter around the AI/data plane.
#
# Control map:
#   Residency + exfiltration control (SPEC 2): a service perimeter draws a logical boundary
#         around the sovereignty-critical APIs market-intelligence uses (Vertex / Agent Platform, Discovery
#         Engine File Search, Model Armor, Logging, Cloud Trace, KMS). Research output and
#         the audit log cannot be read across the boundary to a non-Singapore project, which
#         is what keeps the corpus and decision record in-country.
#   Least surface (SPEC 3): only the services market-intelligence actually calls are inside the perimeter.
#
# Two toggles:
#   var.enable_vpc_sc  : create the perimeter at all (count).
#   var.vpc_sc_enforce : enforce (true) vs DRY-RUN/audit (false, default). Good practice is
#                        to apply with false first, watch the dry-run violation logs (the
#                        monitoring.tf vpc_sc_denials alert surfaces them), add operators to
#                        an access level, then flip to true. In dry-run the restricted
#                        services live in `spec` (audited, not enforced) and `status` stays
#                        open.
#
# DEPLOY-ORDER CAVEAT: enabling enforcement before the resources exist (or before the CI /
# operator identity is on an access level) denies those API calls and fails the apply. Apply
# everything with vpc_sc_enforce = false first, add operators, then re-apply with true.
#
# NOTE on egress: VPC-SC governs access to GOOGLE APIs across perimeters, not arbitrary
# internet egress. Public-web grounding (Grounding with Google Search) reaches Google APIs
# inside the perimeter; any non-Google fetch is a VPC firewall / Cloud NAT concern.
# verify: https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/access_context_manager_service_perimeter

locals {
  perimeter_restricted_services = [
    "aiplatform.googleapis.com",
    "discoveryengine.googleapis.com",
    "modelarmor.googleapis.com",
    "logging.googleapis.com",
    "cloudtrace.googleapis.com",
    "cloudkms.googleapis.com",
  ]

  # Access level is created only when operators are supplied AND the perimeter is enabled.
  make_access_level = var.enable_vpc_sc && length(var.operator_members) > 0
  access_level_names = local.make_access_level ? [
    "accessPolicies/${var.access_policy_id}/accessLevels/mkt_operators"
  ] : []
}

# Allow named operator/CI identities to reach the restricted APIs from outside the perimeter.
resource "google_access_context_manager_access_level" "operators" {
  count = local.make_access_level ? 1 : 0

  parent = "accessPolicies/${var.access_policy_id}"
  name   = "accessPolicies/${var.access_policy_id}/accessLevels/mkt_operators"
  title  = "mkt_operators"

  basic {
    conditions {
      members = var.operator_members
    }
  }
}

resource "google_access_context_manager_service_perimeter" "mkt" {
  count = var.enable_vpc_sc ? 1 : 0

  parent = "accessPolicies/${var.access_policy_id}"
  name   = "accessPolicies/${var.access_policy_id}/servicePerimeters/mkt_market_intel_sg"
  title  = "mkt_market_intel_sg"

  perimeter_type = "PERIMETER_TYPE_REGULAR"

  # Dry-run (audit) until var.vpc_sc_enforce flips to true.
  use_explicit_dry_run_spec = !var.vpc_sc_enforce

  # Enforced configuration. In dry-run this stays open (nothing restricted); in enforce mode
  # it carries the restricted-service boundary.
  status {
    resources           = ["projects/${data.google_project.this.number}"]
    restricted_services = var.vpc_sc_enforce ? local.perimeter_restricted_services : []
    access_levels       = var.vpc_sc_enforce ? local.access_level_names : []

    dynamic "vpc_accessible_services" {
      for_each = var.vpc_sc_enforce ? [1] : []
      content {
        enable_restriction = true
        allowed_services   = local.perimeter_restricted_services
      }
    }
  }

  # Dry-run spec: audited, not enforced. Present only while not enforcing.
  dynamic "spec" {
    for_each = var.vpc_sc_enforce ? [] : [1]
    content {
      resources           = ["projects/${data.google_project.this.number}"]
      restricted_services = local.perimeter_restricted_services
      access_levels       = local.access_level_names

      vpc_accessible_services {
        enable_restriction = true
        allowed_services   = local.perimeter_restricted_services
      }
    }
  }

  depends_on = [google_project_service.required]
}
