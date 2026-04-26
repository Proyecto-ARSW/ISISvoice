terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.90"
    }
  }
  required_version = ">= 1.0"
}

provider "azurerm" {
  features {
    virtual_machine {
      graceful_shutdown = true
    }
  }
}

# Create Resource Group
resource "azurerm_resource_group" "isisvoice" {
  name     = var.resource_group_name
  location = var.location

  tags = {
    Environment = var.environment
    Project     = "ISISvoice"
    ManagedBy   = "Terraform"
  }
}

# Container Registry for ISISvoice image
resource "azurerm_container_registry" "acr" {
  name                = var.container_registry_name
  resource_group_name = azurerm_resource_group.isisvoice.name
  location            = azurerm_resource_group.isisvoice.location
  sku                 = "Basic"
  admin_enabled       = true

  tags = {
    Name = "ISISvoice Registry"
  }
}

# Container Apps Environment
resource "azurerm_container_app_environment" "env" {
  name                = "${var.environment}-cae"
  location            = azurerm_resource_group.isisvoice.location
  resource_group_name = azurerm_resource_group.isisvoice.name

  tags = {
    Name = "ISISvoice Environment"
  }
}

# ISISvoice Container App (with scale-to-zero for cost savings)
resource "azurerm_container_app" "isisvoice" {
  name                         = "${var.app_name}-${var.environment}"
  container_app_environment_id = azurerm_container_app_environment.env.id
  resource_group_name          = azurerm_resource_group.isisvoice.name
  revision_mode                = "Single"

  template {
    container {
      name   = "isisvoice"
      image  = var.isisvoice_image
      cpu    = 0.5
      memory = "1Gi"

      # Environment variables for AWS endpoints
      env {
        name  = "WHISPER_API_URL"
        value = var.whisper_api_url
      }

      env {
        name  = "OLLAMA_BASE_URL"
        value = var.ollama_base_url
      }

      env {
        name  = "MONGODB_URI"
        value = var.mongodb_uri
      }

      env {
        name  = "MONGODB_DB"
        value = var.mongodb_db
      }

      env {
        name  = "JWT_SECRET"
        value = var.jwt_secret
      }

      env {
        name  = "JWT_ALGORITHM"
        value = "HS256"
      }

      env {
        name  = "WHISPER_MODEL"
        value = var.whisper_model
      }

      env {
        name  = "WHISPER_LANGUAGE"
        value = var.whisper_language
      }

      env {
        name  = "WHISPER_TIMEOUT_SECONDS"
        value = "45"
      }

      env {
        name  = "OLLAMA_MODEL"
        value = var.ollama_model
      }

      env {
        name  = "OLLAMA_TIMEOUT_SECONDS"
        value = "12"
      }

      env {
        name  = "MONGO_SERVER_SELECTION_TIMEOUT_MS"
        value = "6000"
      }

      env {
        name  = "MONGO_CONNECT_TIMEOUT_MS"
        value = "6000"
      }

      env {
        name  = "MONGO_SOCKET_TIMEOUT_MS"
        value = "10000"
      }

      env {
        name  = "MONGO_OPERATION_TIMEOUT_SECONDS"
        value = "2.5"
      }

      env {
        name  = "SESSION_QUEUE_MAX_SIZE"
        value = "32"
      }

      env {
        name  = "MAX_HISTORY_MESSAGES"
        value = "40"
      }
    }

    min_replicas = var.min_replicas
    max_replicas = var.max_replicas
  }

  ingress {
    allow_insecure_connections = false
    external_enabled           = true
    target_port                = 8000
    transport                  = "http"

    traffic_weight {
      latest_revision = true
      percent         = 100
    }
  }

  tags = {
    Name = "ISISvoice API"
  }
}

# Output the URL
output "isisvoice_url" {
  value       = azurerm_container_app.isisvoice.latest_revision_fqdn
  description = "ISISvoice API public URL"
}

output "container_registry_url" {
  value       = azurerm_container_registry.acr.login_server
  description = "Container Registry login server"
}

output "resource_group_id" {
  value       = azurerm_resource_group.isisvoice.id
  description = "Resource Group ID"
}
