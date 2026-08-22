# kms.tf : Regional Customer-Managed Encryption Key (CMEK) in Singapore.
#
# Control map:
#   CMEK does NOT cascade: a CMEK on one resource does not automatically protect data that
#         resource hands to another service. Each managed service that touches Mkt1 data
#         (the Cloud Run revision, the GenAI File Search store via Discovery Engine, Vertex /
#         Agent Platform runtime state, and the WORM log bucket) is granted use of THIS key
#         explicitly below. One regional key ring + crypto key; no project-wide grant.
#   Residency (SPEC 2): the key ring location is var.region : a regional key, never the
#         global / multi-region key. Regional CMEK is what pins crypto material in-country.

resource "google_kms_key_ring" "mkt" {
  name     = "mkt-market-intel-ring"
  location = var.region # the selected region : regional, in-country key material (SPEC 2)

  depends_on = [google_project_service.required]
}

resource "google_kms_crypto_key" "mkt" {
  name     = "mkt-market-intel-cmek"
  key_ring = google_kms_key_ring.mkt.id

  purpose         = "ENCRYPT_DECRYPT"
  rotation_period = "7776000s" # 90 days : periodic rotation for key hygiene

  version_template {
    algorithm        = "GOOGLE_SYMMETRIC_ENCRYPTION"
    protection_level = "SOFTWARE"
  }

  lifecycle {
    # A destroyed key is unrecoverable and would strand all CMEK-encrypted data.
    prevent_destroy = true
  }
}

# --------------------------------------------------------------------------- #
# Grant each service agent the right to use the key. CMEK does not cascade:
# every service that encrypts with this key needs its OWN binding here.
# --------------------------------------------------------------------------- #
data "google_project" "this" {
  project_id = var.project_id
}

# Cloud Run service agent (encrypts the serving revision with CMEK).
resource "google_kms_crypto_key_iam_member" "run" {
  crypto_key_id = google_kms_crypto_key.mkt.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@serverless-robot-prod.iam.gserviceaccount.com"
}

# Discovery Engine (GenAI File Search / Agent Search) service agent : CMEK on the corpus index.
resource "google_kms_crypto_key_iam_member" "discoveryengine" {
  crypto_key_id = google_kms_crypto_key.mkt.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-discoveryengine.iam.gserviceaccount.com"
}

# Vertex AI / Agent Platform service agent : CMEK on reasoning / eval / agent state.
resource "google_kms_crypto_key_iam_member" "aiplatform" {
  crypto_key_id = google_kms_crypto_key.mkt.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-aiplatform.iam.gserviceaccount.com"
}

# Cloud Logging service agent : CMEK on the WORM audit bucket.
resource "google_kms_crypto_key_iam_member" "logging" {
  crypto_key_id = google_kms_crypto_key.mkt.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-logging.iam.gserviceaccount.com"
}
