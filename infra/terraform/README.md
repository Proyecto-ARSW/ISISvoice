# Terraform Deployment Guide - Voice Medical Triage Service

## Overview

This Terraform configuration deploys the Voice Medical Triage Service to AWS using:
- **ECS Fargate** for containerized application hosting
- **Application Load Balancer (ALB)** for traffic distribution
- **Auto Scaling** based on CPU and memory metrics
- **CloudWatch Logs** for centralized logging
- **MongoDB Atlas** for database persistence

## Prerequisites

1. **Terraform** >= 1.0
   ```bash
   brew install terraform  # macOS
   # or download from https://www.terraform.io/downloads.html
   ```

2. **AWS Account** with credentials configured
   ```bash
   aws configure
   ```

3. **Docker Image** pushed to AWS ECR or a registry
   ```bash
   # Build locally
   docker build -f src/app/Dockerfile -t voice-medical:latest .
   
   # Push to ECR
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com
   docker tag voice-medical:latest 123456789.dkr.ecr.us-east-1.amazonaws.com/voice-medical:latest
   docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/voice-medical:latest
   ```

4. **MongoDB Atlas** cluster created and connection string available

## Quick Start

### 1. Create Terraform Variables File

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your values:
- `container_image`: Your Docker image URI
- `mongodb_uri`: MongoDB Atlas connection string
- `aws_region`: Your preferred AWS region
- Other configurations as needed

### 2. Initialize Terraform

```bash
terraform init
```

### 3. Review Changes

```bash
terraform plan
```

### 4. Deploy

```bash
terraform apply
```

When prompted, type `yes` to confirm.

### 5. Get Outputs

```bash
terraform output
```

Your API endpoint will be displayed as `api_endpoint`.

## Configuration Documentation

### Environment Levels

#### Development (Dev)
```hcl
environment  = "dev"
ecs_task_cpu = 512
ecs_task_memory = 1024
ecs_desired_count = 1
ecs_max_capacity = 2
```

#### Staging
```hcl
environment  = "staging"
ecs_task_cpu = 1024
ecs_task_memory = 2048
ecs_desired_count = 2
ecs_max_capacity = 3
```

#### Production
```hcl
environment  = "prod"
ecs_task_cpu = 2048
ecs_task_memory = 4096
ecs_desired_count = 3
ecs_max_capacity = 10
```

### Whisper Model Selection

| Model     | Size  | Accuracy | Resource Usage | Suitable For |
|-----------|-------|----------|----------------|--------------|
| tiny      | 39M   | Low      | Very Low       | Testing      |
| base      | 140M  | Medium   | Low            | Dev          |
| small     | 244M  | Good     | Medium         | Dev/Staging  |
| medium    | 769M  | Better   | Medium-High    | Staging      |
| large     | 2.9G  | Very Good| High           | Production   |
| large-v3  | 2.9G  | Excellent| High           | Production   |

## Monitoring & Scaling

### Check Service Status

```bash
# Get service details
aws ecs describe-services \
  --cluster voice-medical-cluster \
  --services voice-medical-service \
  --region us-east-1

# View logs
aws logs tail /ecs/voice-medical --follow
```

### Manual Scaling

Change `ecs_desired_count` in `terraform.tfvars` and apply:

```bash
terraform apply
```

### Auto Scaling Policies

The configuration includes automatic scaling based on:
- **CPU**: Target 70% utilization
- **Memory**: Target 80% utilization

Min/max capacity defined by:
- `ecs_min_capacity`
- `ecs_max_capacity`

## Cost Optimization

### Dev Environment
- Use smaller models: `tiny`, `base`
- Reduce `ecs_desired_count` to 1
- Use Spot instances if cost conscious
- Deploy in off-peak hours only

### Production Environment
- Use `large-v3` model for accuracy
- Set appropriate `ecs_desired_count` (minimum 2 for HA)
- Enable CloudWatch for monitoring
- Use reserved ECS capacity for predictable workloads

## Updating the Application

### Update Container Image

```bash
# 1. Build new Docker image
docker build -f src/app/Dockerfile -t voice-medical:v1.1 .

# 2. Push to registry
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/voice-medical:v1.1

# 3. Update terraform.tfvars
sed -i 's|voice-medical:latest|voice-medical:v1.1|' terraform.tfvars

# 4. Redeploy
terraform apply
```

## Troubleshooting

### Service Not Reaching Healthy State

```bash
# Check task logs
aws logs tail /ecs/voice-medical --follow

# Check ECS task status
aws ecs list-tasks --cluster voice-medical-cluster --region us-east-1
```

### Database Connection Issues

```bash
# Verify MongoDB connection
mongosh "Your connection string"

# Check environment variables in running task
aws ecs describe-task-definition --task-definition voice-medical
```

### Load Balancer Not Routing Traffic

```bash
# Check target group health
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:... \
  --region us-east-1
```

## Cleanup

### Destroy Infrastructure

⚠️ **Warning**: This will delete all resources!

```bash
terraform destroy
```

## Files Structure

```
infra/terraform/
├── main.tf                    # Main configuration
├── variables.tf               # Input variables
├── outputs.tf                 # Output values
├── providers.tf               # Provider configuration
├── terraform.tfvars.example   # Example variables
├── README.md                  # This file
└── modules/
    └── aws/
        ├── main.tf            # AWS-specific resources
        └── variables.tf        # AWS module variables
```

## Best Practices

1. ✅ Always run `terraform plan` before `apply`
2. ✅ Use separate `terraform.tfvars` for each environment
3. ✅ Store sensitive data (MongoDB URI) in AWS Secrets Manager
4. ✅ Enable state locking (uncomment backend config in main.tf)
5. ✅ Regularly update Terraform and provider versions
6. ✅ Use descriptive tags for easy resource identification
7. ✅ Monitor costs with AWS Cost Explorer

## Support & Documentation

- [AWS ECS Documentation](https://docs.aws.amazon.com/ecs/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [MongoDB Atlas](https://www.mongodb.com/docs/atlas/)
