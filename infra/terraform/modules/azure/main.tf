# Azure module scaffold for future deployment
# Intentionally minimal in this phase.

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

# TODO: Add Azure Container Apps/AKS resources in next phase.

output "status" {
  value       = "azure-module-scaffolded"
  description = "Azure module scaffold created"
}
