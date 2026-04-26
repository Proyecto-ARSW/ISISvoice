# ISISvoice Terraform Deployment (Azure)

This Terraform configuration deploys **ISISvoice API only** on Azure Container Apps. Whisper and Ollama run on AWS and are referenced via environment variables.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│               Azure (ISISvoice)                     │
│  ┌─────────────────────────────────────────────┐   │
│  │  Container Apps (scale-to-zero)             │   │
│  │  - ISISvoice API (FastAPI)                  │   │
│  │  - Endpoints: health, triage, clinical      │   │
│  └─────────────────────────────────────────────┘   │
│                      │                              │
│              MongoDB Atlas (External)               │
└─────────────────────────────────────────────────────┘
         │                          │
         │                          │
    ┌────▼─────┐          ┌────────▼─────┐
    │   AWS    │          │    AWS       │
    │ Whisper  │          │   Ollama     │
    │ (8001)   │          │  (11434)     │
    └──────────┘          └──────────────┘
```

## Prerequisites

1. **Azure Account** with active subscription (different from your personal account)
2. **Terraform** >= 1.0 (install from https://www.terraform.io/downloads)
3. **Azure CLI** (optional, for authentication)
4. **Docker** (to build and push ISISvoice image to ACR)
5. **AWS Instances Running**:
   - Whisper API on port 8001 (EC2 instance or similar)
   - Ollama API on port 11434 (EC2 instance or similar)

## Setup Instructions

### 1. Clone and Navigate

```bash
cd terraform/
```

### 2. Create `.tfvars` File

Copy the example and customize with your values:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and set:
- `isisvoice_image`: Your ACR image URL (build next)
- `whisper_api_url`: AWS Whisper instance IP:8001
- `ollama_base_url`: AWS Ollama instance IP:11434
- `mongodb_uri`: Your MongoDB Atlas connection string
- `jwt_secret`: Your existing JWT secret
- `container_registry_name`: Unique ACR name (e.g., `isisvoiceacr2026`)

### 3. Build and Push ISISvoice Image

Before deploying, build the Docker image and push it to Azure Container Registry:

```bash
# Authenticate with Azure
az login

# Set your subscription
az account set --subscription "YOUR_SUBSCRIPTION_ID"

# Create ACR (if not already created by Terraform)
az acr create \
  --resource-group rg-isisvoice-prod \
  --name isisvoiceacr \
  --sku Basic

# Build and push image
az acr build \
  --registry isisvoiceacr \
  --image isisvoice:latest \
  --file src/app/Dockerfile .

# Get the image URL
az acr show \
  --name isisvoiceacr \
  --query loginServer \
  --output tsv
# Output: isisvoiceacr.azurecr.io
# Update terraform.tfvars: isisvoice_image = "isisvoiceacr.azurecr.io/isisvoice:latest"
```

### 4. Initialize Terraform

```bash
terraform init
```

### 5. Validate Configuration

```bash
terraform validate
```

### 6. Plan Deployment

```bash
terraform plan -out=tfplan
```

Review the output to ensure all resources are correct.

### 7. Apply Configuration

```bash
terraform apply tfplan
```

Wait for completion. You'll see outputs with:
- **ISISvoice API URL**: Your public endpoint
- **Container Registry URL**: For future image pushes
- **Resource Group ID**: For Azure Portal access

### 8. Verify Deployment

```bash
# Test ISISvoice health endpoint
curl https://YOUR_ISISVOICE_URL/speech/health

# Should return something like:
# {"status": "healthy", "service": "speech-service", ...}
```

## Environment Variables in Azure

The Container App automatically sets these from `terraform.tfvars`:

```
WHISPER_API_URL=http://YOUR_WHISPER_AWS_IP:8001
OLLAMA_BASE_URL=http://YOUR_OLLAMA_AWS_IP:11434
MONGODB_URI=mongodb+srv://...
JWT_SECRET=...
```

If AWS IPs change, update `terraform.tfvars` and run:

```bash
terraform apply
```

## Scaling and Cost Optimization

### Auto-Scaling

- **Min replicas**: 0 (scales to zero when idle)
- **Max replicas**: 3 (increases when CPU > 70%)
- **Cooldown**: Respects Azure's default scaling cooldown

To adjust:

```bash
# Edit terraform.tfvars
min_replicas = 0
max_replicas = 5

# Apply changes
terraform apply
```

### Cost Estimation

With `min_replicas = 0` and typical usage patterns:
- **Idle**: ~$0.05/day
- **Light load**: ~$1-2/day
- **Peak load**: ~$3-5/day

Monitor costs in Azure Portal → Cost Management → Cost Analysis.

## Troubleshooting

### Connection to Whisper/Ollama fails

1. Verify AWS instance IPs are correct in `terraform.tfvars`
2. Check AWS Security Groups allow inbound traffic on ports 8001 and 11434
3. Test connectivity:

```bash
# From your machine
curl http://YOUR_WHISPER_AWS_IP:8001/health
curl http://YOUR_OLLAMA_AWS_IP:11434/api/tags
```

### Container won't start

Check logs:

```bash
az containerapp logs show \
  --name isisvoice-production \
  --resource-group rg-isisvoice-prod
```

### MongoDB connection fails

Verify:
- MongoDB URI is correct in `.tfvars`
- Your IP is whitelisted in MongoDB Atlas (Network Access)
- Connection timeouts are appropriate

## Cleanup

To destroy all resources:

```bash
terraform destroy
```

**Caution**: This will delete all Azure resources but NOT MongoDB data.

## Additional Commands

### Check current state

```bash
terraform show
```

### Update only specific resource

```bash
terraform apply -target=azurerm_container_app.isisvoice
```

### Output values

```bash
terraform output
```

## Support

For Azure issues, check:
- Azure Portal: https://portal.azure.com
- Container App logs in Portal
- Terraform docs: https://www.terraform.io/docs

For code issues:
- Check ISISvoice logs
- Verify MongoDB connection
- Test AWS endpoints directly
