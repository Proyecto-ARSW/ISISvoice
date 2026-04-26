variable "location" {
  type        = string
  default     = "eastus"
  description = "Azure region for resources"
}

variable "resource_group_name" {
  type        = string
  default     = "rg-isisvoice-prod"
  description = "Name of the resource group"
}

variable "environment" {
  type        = string
  default     = "production"
  description = "Environment name (production, staging, dev)"
}

variable "app_name" {
  type        = string
  default     = "isisvoice"
  description = "Application name"
}

variable "container_registry_name" {
  type        = string
  default     = "isisvoiceacr"
  description = "Container Registry name (must be globally unique, lowercase)"
}

variable "isisvoice_image" {
  type        = string
  description = "Container image URI for ISISvoice (e.g., isisvoiceacr.azurecr.io/isisvoice:latest)"
}

variable "min_replicas" {
  type        = number
  default     = 0
  description = "Minimum replicas (0 = scale to zero)"
}

variable "max_replicas" {
  type        = number
  default     = 3
  description = "Maximum replicas for autoscaling"
}

# ====================
# AWS Endpoints (Whisper & Ollama)
# ====================
variable "whisper_api_url" {
  type        = string
  description = "Whisper API endpoint on AWS (e.g., http://54.123.45.67:8001)"
}

variable "ollama_base_url" {
  type        = string
  description = "Ollama API endpoint on AWS (e.g., http://54.123.45.67:11434)"
}

variable "whisper_model" {
  type        = string
  default     = "large-v3"
  description = "Whisper model name"
}

variable "whisper_language" {
  type        = string
  default     = "es"
  description = "Default language for Whisper (ISO 639-1 code)"
}

variable "ollama_model" {
  type        = string
  default     = "medical3.1"
  description = "Ollama model name"
}

# ====================
# MongoDB Atlas
# ====================
variable "mongodb_uri" {
  type        = string
  sensitive   = true
  description = "MongoDB Atlas connection string (with credentials)"
}

variable "mongodb_db" {
  type        = string
  default     = "voice_medical"
  description = "MongoDB database name"
}

# ====================
# JWT Security
# ====================
variable "jwt_secret" {
  type        = string
  sensitive   = true
  description = "JWT secret for token signing"
}
