# GCP module scaffold for future deployment
# Intentionally minimal in this phase.

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# TODO: Add Cloud Run/GKE resources in next phase.

output "status" {
  value       = "gcp-module-scaffolded"
  description = "GCP module scaffold created"
}
