# org_policy.tf : Org Policy constraints enforcing in-country residency (defence in depth).
#
# Control map:
#   Residency (SPEC 2): even if someone hand-edits a resource, these org policies REJECT the
#         creation of resources outside the Singapore region. gcp.resourceLocations is the
#         master residency control.
#   No service-account keys: disable exportable SA-key creation : the workloads use Workload
#         Identity (Cloud Run runtime SA), so a long-lived key should never exist. The
#         posture alert in monitoring.tf fires if one is created anyway.
#   Private data plane: deny VM external IPs and require uniform bucket-level access so data
#         and compute stay in-country and private.
#
# Scoped to the project via google_org_policy_policy. To enforce org-wide, move these to an
# org-level policy with parent = "organizations/${var.org_id}".
# verify: https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/org_policy_policy

# Master residency policy: only allow locations inside the selected region.
resource "google_org_policy_policy" "resource_locations" {
  name   = "projects/${var.project_id}/policies/gcp.resourceLocations"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      values {
        # e.g. "in:asia-southeast1-locations" : the selected region plus its sub-locations.
        allowed_values = ["in:${var.region}-locations"]
      }
    }
  }

  depends_on = [google_project_service.required]
}

# Disable exportable service-account key creation : use Workload Identity instead.
resource "google_org_policy_policy" "disable_sa_keys" {
  name   = "projects/${var.project_id}/policies/iam.disableServiceAccountKeyCreation"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      enforce = "TRUE"
    }
  }

  depends_on = [google_project_service.required]
}

# Disable VM external IPs : keep the data plane private.
resource "google_org_policy_policy" "no_external_ip" {
  name   = "projects/${var.project_id}/policies/compute.vmExternalIpAccess"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      deny_all = "TRUE"
    }
  }

  depends_on = [google_project_service.required]
}

# Require uniform bucket-level access (no per-object ACL exfiltration paths).
resource "google_org_policy_policy" "uniform_bucket_access" {
  name   = "projects/${var.project_id}/policies/storage.uniformBucketLevelAccess"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      enforce = "TRUE"
    }
  }

  depends_on = [google_project_service.required]
}
