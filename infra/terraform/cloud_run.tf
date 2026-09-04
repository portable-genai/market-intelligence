# cloud_run.tf : Cloud Run v2 service running the market-intelligence FastAPI image in Singapore.
#
# Control map:
#   Residency (SPEC 2): location is var.region (selected at deploy, allowlist-validated). The
#         revision is encrypted with the regional CMEK key.
#   Least privilege / no keys (SPEC 3): runs as the dedicated runtime SA via Workload
#         Identity (no exported keys). Profile is opted into the managed stack EXPLICITLY
#         (MKT_INTEL_PROFILE=gcp) : an unset env var is "no choice", which binds the SDK-free
#         adapters and refuses every end-user request, so production must set it here.
#   Controlled ingress: internal + load-balancer only; the service is not on the open
#         internet. Pair with an external HTTPS LB + IAP if a browser front door is needed.
#
# Environment variables drive the settings.yaml ${ENV:-default} interpolation, so neither
# code nor the config file changes between environments. No secrets are set here.

resource "google_cloud_run_v2_service" "api" {
  name     = "market-intelligence"
  location = var.region # the selected, allowlisted region (SPEC 2)
  project  = var.project_id

  # Internal + load-balancer ingress : the API is a platform-internal service, not public.
  ingress = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    # Encrypt the revision with the regional CMEK key (CMEK does not cascade : kms.tf binds
    # the Cloud Run service agent to the key).
    encryption_key                   = google_kms_crypto_key.mkt.id
    service_account                  = google_service_account.runtime.email
    max_instance_request_concurrency = 80

    scaling {
      min_instance_count = 1
      max_instance_count = 4
    }

    containers {
      image = var.container_image

      ports {
        container_port = 8100 # matches the Dockerfile EXPOSE / uvicorn port
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      # Opt in to the managed stack EXPLICITLY (an unset variable is refused, not `local`).
      env {
        name  = "MKT_INTEL_PROFILE"
        value = "gcp"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      # The SG market defaults to the asia-southeast1 resident deploy (per-market residency, SPEC 2).
      env {
        name  = "MKT_MARKET"
        value = "SG"
      }
      env {
        name  = "MKT_INTEL_KMS_KEY"
        value = google_kms_crypto_key.mkt.id
      }

      startup_probe {
        http_get {
          path = "/healthz"
          port = 8100
        }
        initial_delay_seconds = 10
        period_seconds        = 5
        failure_threshold     = 6
      }

      liveness_probe {
        http_get {
          path = "/healthz"
          port = 8100
        }
        period_seconds = 30
      }
    }
  }

  depends_on = [
    google_kms_crypto_key_iam_member.run,
    google_project_iam_member.runtime,
  ]
}
