# ========== Deployment Configuration ==========

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name for resource naming and tagging"
  type        = string
  default     = "voice-medical"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
  
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

# ========== Networking ==========

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

# ========== Container Configuration ==========

variable "container_image" {
  description = "Docker image URI (e.g., '123456789.dkr.ecr.us-east-1.amazonaws.com/voice-medical:latest')"
  type        = string
}

variable "ecs_task_cpu" {
  description = "CPU units for ECS task (256, 512, 1024, 2048, 4096)"
  type        = number
  default     = 1024
  
  validation {
    condition     = contains([256, 512, 1024, 2048, 4096], var.ecs_task_cpu)
    error_message = "ECS task CPU must be 256, 512, 1024, 2048, or 4096."
  }
}

variable "ecs_task_memory" {
  description = "Memory (MB) for ECS task"
  type        = number
  default     = 2048
}

variable "ecs_desired_count" {
  description = "Desired number of running ECS tasks"
  type        = number
  default     = 2
}

variable "ecs_min_capacity" {
  description = "Minimum number of ECS tasks for auto-scaling"
  type        = number
  default     = 1
}

variable "ecs_max_capacity" {
  description = "Maximum number of ECS tasks for auto-scaling"
  type        = number
  default     = 5
}

# ========== Database Configuration ==========

variable "mongodb_uri" {
  description = "MongoDB connection URI (MongoDB Atlas recommended)"
  type        = string
  sensitive   = true
  
  validation {
    condition     = startswith(var.mongodb_uri, "mongodb")
    error_message = "MongoDB URI must start with 'mongodb' or 'mongodb+srv'."
  }
}

variable "mongodb_db" {
  description = "MongoDB database name"
  type        = string
  default     = "voice_medical"
}

# ========== AI Model Configuration ==========

variable "whisper_model" {
  description = "Whisper model size (tiny, base, small, medium, large, large-v3)"
  type        = string
  default     = "large-v3"
  
  validation {
    condition     = contains(["tiny", "base", "small", "medium", "large", "large-v3"], var.whisper_model)
    error_message = "Whisper model must be one of: tiny, base, small, medium, large, large-v3."
  }
}

variable "whisper_language" {
  description = "Language code for Whisper (ISO 639-1)"
  type        = string
  default     = "es"
  
  validation {
    condition     = length(var.whisper_language) == 2
    error_message = "Language code must be ISO 639-1 format (e.g., 'es', 'en')."
  }
}

