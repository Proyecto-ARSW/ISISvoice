terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Uncomment to use remote state storage
  # backend "s3" {
  #   bucket         = "voice-medical-tfstate"
  #   key            = "prod/terraform.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   dynamodb_table = "terraform-locks"
  # }
}

# ========== Local Variables ==========

locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    CreatedAt   = timestamp()
    ManagedBy   = "Terraform"
  }
}

# ========== AWS Module (Main Deployment) ==========

module "aws_deployment" {
  source = "./modules/aws"

  aws_region              = var.aws_region
  project_name            = var.project_name
  environment             = var.environment
  vpc_cidr                = var.vpc_cidr
  ecs_task_cpu            = var.ecs_task_cpu
  ecs_task_memory         = var.ecs_task_memory
  ecs_desired_count       = var.ecs_desired_count
  ecs_min_capacity        = var.ecs_min_capacity
  ecs_max_capacity        = var.ecs_max_capacity
  container_image         = var.container_image
  mongodb_uri             = var.mongodb_uri
  mongodb_db              = var.mongodb_db
  whisper_model           = var.whisper_model
  whisper_language        = var.whisper_language
}

