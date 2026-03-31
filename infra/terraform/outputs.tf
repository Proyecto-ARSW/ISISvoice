# ========== API Access ==========

output "api_endpoint" {
  description = "API endpoint URL"
  value       = module.aws_deployment.alb_dns_name
  
  depends_on = [module.aws_deployment]
}

output "api_url" {
  description = "Full API URL with HTTP protocol"
  value       = "http://${module.aws_deployment.alb_dns_name}"
  
  depends_on = [module.aws_deployment]
}

output "api_docs_url" {
  description = "Swagger API documentation URL"
  value       = "http://${module.aws_deployment.alb_dns_name}/docs"
  
  depends_on = [module.aws_deployment]
}

# ========== ECS Service Details ==========

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = module.aws_deployment.ecs_cluster_name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = module.aws_deployment.ecs_service_name
}

# ========== Deployment Info ==========

output "project_name" {
  description = "Project name"
  value       = var.project_name
}

output "environment" {
  description = "Deployment environment"
  value       = var.environment
}

output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}

# ========== Important Instructions ==========

output "next_steps" {
  description = "Important instructions after deployment"
  value = <<-EOT
    
    DEPLOYMENT COMPLETE
    
    API Endpoint:  http://${module.aws_deployment.alb_dns_name}
    API Docs:      http://${module.aws_deployment.alb_dns_name}/docs
    
    Health checks:
    - /api/v1/live      : Liveness probe
    - /api/v1/ready     : Readiness probe
    - /api/v1/health    : Full health status
    
    Main Endpoints:
    - POST /api/v1/triage/voice-input    → Process voice audio
    - POST /api/v1/triage/text-input     → Process text input
    - GET  /api/v1/triage/record/{cedula}  → Get triage records
    - POST /api/v1/patient/info          → Create patient info
    
    Monitor your deployment:
    - AWS CloudWatch Logs: /ecs/${var.project_name}
    - ECS Cluster: ${module.aws_deployment.ecs_cluster_name}
    - ECS Service: ${module.aws_deployment.ecs_service_name}
    
    To scale the service:
    - Update ecs_desired_count in terraform.tfvars and run 'terraform apply'
    - Auto-scaling policies are in place (CPU: 70%, Memory: 80%)
    
    To destroy the infrastructure:
    - terraform destroy
    
  EOT
}
