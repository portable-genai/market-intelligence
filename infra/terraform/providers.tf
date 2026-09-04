# providers.tf : Provider pinning for the market-intelligence Market Intelligence sovereign deploy.
#
# Control map (this repo has no numbered General Principles; controls cite SPEC sections):
#   Residency (SPEC 2): every provider call is pinned to a single in-country region. The
#         default deploy region is asia-southeast1 (Singapore, the SG market), overridable
#         within the residency allowlist. There is no
#         global / multi-region default endpoint.
#   No lock-in (SPEC 3): Terraform is the only place infra is described; the application
#         talks to ports, not to these resources.
#
# google-beta is declared for resources only exposed on the beta surface (some Access
# Context Manager fields, org_policy v2 surfaces) on the pinned provider line.

terraform {
  required_version = ">= 1.9.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0" # 6.x line : current GA surface (mid-2026)
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
  }
}

# Primary (GA) provider : every resource defaults to the pinned region.
provider "google" {
  project = var.project_id
  region  = var.region # the selected region : pinned, never global
}

# Beta provider : same project/region, used only where a resource needs it.
provider "google-beta" {
  project = var.project_id
  region  = var.region
}
