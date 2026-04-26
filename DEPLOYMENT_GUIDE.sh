#!/bin/bash

# ISISvoice Complete Deployment Guide
# This script helps you deploy ISISvoice across Azure (API) and AWS (Models)
# Prerequisites:
# - AWS Account with EC2 access
# - Azure Account with student benefits
# - Docker installed locally

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         ISISvoice Deployment Guide (Azure + AWS)              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================================
# STEP 1: Deploy Whisper on AWS
# ============================================================================
echo "STEP 1: Deploy Whisper on AWS"
echo "==============================="
echo ""
echo "1. Launch EC2 instance (Ubuntu 22.04 LTS)"
echo "   - Type: t3.medium or larger (Whisper is CPU-intensive)"
echo "   - Storage: 30GB EBS"
echo "   - Security Group: Allow inbound on port 8001 from your IP"
echo ""
echo "2. Connect via SSH:"
echo "   $ ssh -i your-key.pem ubuntu@YOUR_WHISPER_IP"
echo ""
echo "3. Run setup script:"
echo "   $ curl -s https://raw.githubusercontent.com/your-repo/whisper-setup.sh | bash"
echo ""
echo "   Or manually:"
echo "   $ sudo apt update && sudo apt install -y python3.11 pip"
echo "   $ pip install openai-whisper fastapi uvicorn python-multipart"
echo "   $ git clone https://github.com/your-repo/whisper-server.git"
echo "   $ cd whisper-server"
echo "   $ nohup python3 server.py > whisper.log 2>&1 &"
echo ""
echo "4. Verify Whisper is running:"
echo "   $ curl http://YOUR_WHISPER_IP:8001/health"
echo ""
echo "5. Record your Whisper AWS IP: ____________________"
echo ""
read -p "Press Enter after Whisper is deployed and record the IP..."

WHISPER_IP=""
while [ -z "$WHISPER_IP" ]; do
  read -p "Enter your Whisper AWS instance IP: " WHISPER_IP
done

# ============================================================================
# STEP 2: Deploy Ollama on AWS
# ============================================================================
echo ""
echo "STEP 2: Deploy Ollama on AWS"
echo "=============================="
echo ""
echo "1. Launch another EC2 instance (Ubuntu 22.04 LTS)"
echo "   - Type: t3.xlarge or larger (Ollama needs more memory)"
echo "   - Storage: 50GB EBS (for model files)"
echo "   - Security Group: Allow inbound on port 11434"
echo ""
echo "2. Connect via SSH:"
echo "   $ ssh -i your-key.pem ubuntu@YOUR_OLLAMA_IP"
echo ""
echo "3. Install Ollama:"
echo "   $ curl -s https://ollama.ai/install.sh | sh"
echo "   $ sudo systemctl start ollama"
echo ""
echo "4. Pull your model (in background - takes time):"
echo "   $ ollama pull medical3.1"
echo "   # This downloads ~10GB, so run in tmux or nohup:"
echo "   $ nohup ollama pull medical3.1 > ollama.log 2>&1 &"
echo ""
echo "5. Verify Ollama is running:"
echo "   $ curl http://YOUR_OLLAMA_IP:11434/api/tags"
echo ""
echo "6. Record your Ollama AWS IP: ____________________"
echo ""
read -p "Press Enter after Ollama is deployed and record the IP..."

OLLAMA_IP=""
while [ -z "$OLLAMA_IP" ]; do
  read -p "Enter your Ollama AWS instance IP: " OLLAMA_IP
done

# ============================================================================
# STEP 3: Build ISISvoice Docker Image
# ============================================================================
echo ""
echo "STEP 3: Build ISISvoice Docker Image"
echo "======================================"
echo ""
echo "Building ISISvoice image locally..."
echo ""

docker build -t isisvoice:latest -f src/app/Dockerfile .

echo "✓ Image built: isisvoice:latest"
echo ""

# ============================================================================
# STEP 4: Push to Azure Container Registry
# ============================================================================
echo ""
echo "STEP 4: Push Image to Azure Container Registry"
echo "==============================================="
echo ""
echo "1. First, authenticate with Azure:"
echo "   $ az login"
echo ""
echo "2. Get your ACR details:"
echo "   $ az acr list --query '[].loginServer' -o tsv"
echo ""
read -p "Enter your ACR registry name (e.g., isisvoiceacr): " ACR_NAME

ACR_URL="${ACR_NAME}.azurecr.io"

echo ""
echo "3. Tag your image:"
echo "   $ docker tag isisvoice:latest ${ACR_URL}/isisvoice:latest"
echo ""
echo "4. Push to ACR:"
echo "   $ az acr build --registry ${ACR_NAME} --image isisvoice:latest -f src/app/Dockerfile ."
echo ""

read -p "Press Enter after pushing to ACR..."

# ============================================================================
# STEP 5: Configure Terraform
# ============================================================================
echo ""
echo "STEP 5: Configure Terraform Variables"
echo "======================================"
echo ""
echo "Creating terraform.tfvars with your settings..."
echo ""

cat > terraform/terraform.tfvars << EOF
# ====================
# Azure Configuration
# ====================
location              = "eastus"
resource_group_name   = "rg-isisvoice-prod"
environment           = "production"
container_registry_name = "${ACR_NAME}"

# ====================
# Container Image
# ====================
isisvoice_image = "${ACR_URL}/isisvoice:latest"

# ====================
# Autoscaling
# ====================
min_replicas = 0  # Scale to zero when idle
max_replicas = 3

# ====================
# AWS Endpoints
# ====================
whisper_api_url = "http://${WHISPER_IP}:8001"
ollama_base_url = "http://${OLLAMA_IP}:11434"

# ====================
# Whisper Configuration
# ====================
whisper_model    = "large-v3"
whisper_language = "es"

# ====================
# Ollama Configuration
# ====================
ollama_model = "medical3.1"

# ====================
# MongoDB Atlas
# ====================
mongodb_uri = "mongodb+srv://christianromerom_db_user:JwLpY7RmKn2XZhOm@siti.oz3u7fx.mongodb.net/?appName=SITI"
mongodb_db  = "voice_medical"

# ====================
# JWT Secret
# ====================
jwt_secret = "ASCLEPIO_ARSW-SECRET-2026-PROYECTO-HOSPITALARIO-CORE"
EOF

echo "✓ terraform.tfvars created"
echo ""

# ============================================================================
# STEP 6: Deploy to Azure with Terraform
# ============================================================================
echo ""
echo "STEP 6: Deploy ISISvoice to Azure"
echo "==================================="
echo ""
echo "1. Navigate to terraform directory:"
echo "   $ cd terraform"
echo ""
echo "2. Initialize Terraform:"
echo "   $ terraform init"
echo ""
echo "3. Review planned changes:"
echo "   $ terraform plan"
echo ""
echo "4. Apply configuration:"
echo "   $ terraform apply"
echo ""
echo "5. Record your ISISvoice URL from the output"
echo ""

read -p "Press Enter after Terraform deployment completes..."

read -p "Enter your ISISvoice URL (from terraform output): " ISISVOICE_URL

# ============================================================================
# STEP 7: Verify All Services
# ============================================================================
echo ""
echo "STEP 7: Verify Deployment"
echo "=========================="
echo ""
echo "Testing all services..."
echo ""

echo "1. Whisper health check:"
curl -s "http://${WHISPER_IP}:8001/health" || echo "⚠ Whisper not responding"
echo ""

echo "2. Ollama health check:"
curl -s "http://${OLLAMA_IP}:11434/api/tags" || echo "⚠ Ollama not responding"
echo ""

echo "3. ISISvoice health check:"
curl -s "${ISISVOICE_URL}/speech/health" || echo "⚠ ISISvoice not responding"
echo ""

# ============================================================================
# STEP 8: Test Complete Flow
# ============================================================================
echo ""
echo "STEP 8: Test Complete Flow"
echo "==========================="
echo ""
echo "Testing triage endpoint (requires audio file):"
echo ""
echo "$ curl -X POST ${ISISVOICE_URL}/triage/process \\"
echo "  -H 'Authorization: Bearer YOUR_JWT_TOKEN' \\"
echo "  -F 'audio=@test-audio.wav' \\"
echo "  -F 'patient_id=test-patient'"
echo ""

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    DEPLOYMENT SUMMARY                         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "✓ Whisper deployed on AWS:"
echo "  URL: http://${WHISPER_IP}:8001"
echo ""
echo "✓ Ollama deployed on AWS:"
echo "  URL: http://${OLLAMA_IP}:11434"
echo ""
echo "✓ ISISvoice deployed on Azure:"
echo "  URL: ${ISISVOICE_URL}"
echo ""
echo "✓ MongoDB Atlas (existing):"
echo "  Cluster: siti.oz3u7fx.mongodb.net"
echo "  Database: voice_medical"
echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "1. Configure firewall rules in AWS to limit access to your IP"
echo "2. Set up CloudWatch alarms for AWS instances (CPU, memory)"
echo "3. Test the complete flow with a sample audio file"
echo "4. Set up CI/CD pipeline for future updates"
echo ""
echo "Documentation: See terraform/README.md for detailed instructions"
echo ""
