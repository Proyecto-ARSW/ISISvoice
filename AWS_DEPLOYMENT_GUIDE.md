# ISISvoice AWS Deployment Guide

This guide covers deploying **Whisper** (ASR) and **Ollama** (LLM) on separate AWS EC2 instances.

## Architecture

```
AWS EC2 Instance 1 (Whisper)         AWS EC2 Instance 2 (Ollama)
┌──────────────────────────────┐    ┌──────────────────────────────┐
│  Ubuntu 22.04 LTS            │    │  Ubuntu 22.04 LTS            │
│  ┌────────────────────────┐  │    │  ┌────────────────────────┐  │
│  │ openai-whisper         │  │    │  │ Ollama Server          │  │
│  │ FastAPI Server         │  │    │  │                        │  │
│  │ Port: 8001             │  │    │  │ Port: 11434            │  │
│  └────────────────────────┘  │    │  └────────────────────────┘  │
│  Elastic IP: Static          │    │  Elastic IP: Static          │
│  Security Group: sg-whisper  │    │  Security Group: sg-ollama   │
└──────────────────────────────┘    └──────────────────────────────┘
         ▲                                    ▲
         │ (calls for transcription)         │ (calls for inference)
         └────────────────┬───────────────────┘
                          │
                    Azure Container Apps
                    (ISISvoice API)
```

## Prerequisites

- AWS Account with EC2 access
- SSH key pair created in AWS
- Security Groups configured for inbound traffic
- Basic knowledge of AWS EC2

## Instance Sizing Recommendations

### Whisper Instance

- **Instance Type**: `t3.medium` or `t3a.large`
  - CPU: 2-4 vCPUs
  - Memory: 4-8 GB
- **Storage**: 30 GB EBS (gp3)
- **Cost**: ~$25-40/month (t3.medium running 24/7)

**Performance**:
- Inference time: 5-15s for 30s audio clip (depends on model size)
- Throughput: ~4-8 concurrent requests

### Ollama Instance

- **Instance Type**: `t3.xlarge` or `g4dn.xlarge` (if budget allows GPU)
  - CPU: 4-8 vCPUs
  - Memory: 16-32 GB
- **Storage**: 50 GB EBS (gp3) for model files
- **Cost**: ~$50-100/month (t3.xlarge running 24/7)

**Performance**:
- Inference time: 2-5s for typical queries (with large models)
- Throughput: ~2-3 concurrent requests

## Step-by-Step Deployment

### 1. Launch Whisper Instance

#### 1a. Create EC2 Instance

```bash
# Using AWS CLI
aws ec2 run-instances \
  --image-ids ami-0c55b159cbfafe1f0 \  # Ubuntu 22.04 LTS in us-east-1
  --instance-type t3.medium \
  --key-name your-key-pair \
  --security-groups whisper-sg \
  --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3}" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=whisper-server}]"
```

Or use AWS Console:
1. EC2 Dashboard → Instances → Launch Instance
2. Choose Ubuntu 22.04 LTS AMI
3. Instance type: t3.medium
4. Configure storage: 30 GB gp3
5. Add security group: Allow inbound on port 8001

#### 1b. Allocate Elastic IP

```bash
# Get an Elastic IP (Static Public IP)
aws ec2 allocate-address --domain vpc

# Associate with Whisper instance
aws ec2 associate-address \
  --allocation-id eipalloc-xxxxxxxxx \
  --instance-id i-xxxxxxxxx
```

Record this IP: **WHISPER_IP = _______________**

#### 1c. Connect and Setup

```bash
# SSH into instance
ssh -i your-key.pem ubuntu@WHISPER_IP

# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y \
  python3.11 \
  python3.11-venv \
  python3-pip \
  git \
  wget \
  curl

# Create virtual environment
python3.11 -m venv /opt/whisper-env
source /opt/whisper-env/bin/activate

# Install Whisper and dependencies
pip install --upgrade pip
pip install openai-whisper fastapi uvicorn python-multipart torch torchvision torchaudio
```

#### 1d. Create Whisper Server Script

```bash
# Create server.py
cat > /opt/whisper-server.py << 'EOF'
import base64
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import whisper
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Whisper API Server")

# Load model on startup
MODEL_SIZE = "large-v3"
model = whisper.load_model(MODEL_SIZE)
logger.info(f"Model {MODEL_SIZE} loaded successfully")

class TranscriptionRequest(BaseModel):
    audio_base64: str
    language: str = "es"
    file_name: str = "audio.wav"

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "whisper-api",
        "model": MODEL_SIZE,
        "version": "1.0"
    }

@app.post("/transcribe")
async def transcribe(request: TranscriptionRequest):
    try:
        # Decode base64 audio
        audio_bytes = base64.b64decode(request.audio_base64)
        
        # Save to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        
        # Transcribe
        result = model.transcribe(
            tmp_path,
            language=request.language,
            verbose=False
        )
        
        # Cleanup
        import os
        os.remove(tmp_path)
        
        return {
            "transcription": result['text'],
            "language": request.language,
            "model": MODEL_SIZE
        }
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, workers=1)
EOF
```

#### 1e. Start Whisper Server

```bash
# Run in background
nohup /opt/whisper-env/bin/python /opt/whisper-server.py > /var/log/whisper.log 2>&1 &

# Or create systemd service (recommended)
sudo tee /etc/systemd/system/whisper.service > /dev/null << 'EOF'
[Unit]
Description=Whisper API Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt
Environment="PATH=/opt/whisper-env/bin"
ExecStart=/opt/whisper-env/bin/python /opt/whisper-server.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable whisper
sudo systemctl start whisper
sudo systemctl status whisper
```

#### 1f. Verify Whisper

```bash
# Test from the instance
curl http://localhost:8001/health

# Test from your local machine
curl http://WHISPER_IP:8001/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "whisper-api",
  "model": "large-v3",
  "version": "1.0"
}
```

---

### 2. Launch Ollama Instance

#### 2a. Create EC2 Instance

```bash
aws ec2 run-instances \
  --image-ids ami-0c55b159cbfafe1f0 \
  --instance-type t3.xlarge \
  --key-name your-key-pair \
  --security-groups ollama-sg \
  --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=50,VolumeType=gp3}" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=ollama-server}]"
```

#### 2b. Allocate Elastic IP

```bash
aws ec2 allocate-address --domain vpc
aws ec2 associate-address \
  --allocation-id eipalloc-yyyyyyyyy \
  --instance-id i-yyyyyyyyy
```

Record this IP: **OLLAMA_IP = _______________**

#### 2c. Connect and Setup

```bash
ssh -i your-key.pem ubuntu@OLLAMA_IP

# Update system
sudo apt update && sudo apt upgrade -y

# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service
sudo systemctl start ollama
sudo systemctl enable ollama

# Verify service
sudo systemctl status ollama
```

#### 2d. Pull Medical Model (Background)

This takes 10-30 minutes depending on model size and connection.

```bash
# Pull model in background
nohup ollama pull medical3.1 > /var/log/ollama-pull.log 2>&1 &

# Monitor progress
tail -f /var/log/ollama-pull.log

# Or use tmux for persistent session
tmux new-session -d -s ollama "ollama pull medical3.1"
tmux capture-pane -t ollama -p  # check status
```

#### 2e. Verify Ollama

```bash
# Check loaded models
curl http://localhost:11434/api/tags

# Test inference (only after model is fully loaded)
curl http://localhost:11434/api/generate \
  -d '{"model": "medical3.1", "prompt": "Hola", "stream": false}'
```

---

### 3. Configure Security Groups

#### For Whisper SG

```bash
aws ec2 authorize-security-group-ingress \
  --group-id sg-whisper \
  --protocol tcp \
  --port 8001 \
  --cidr YOUR_OFFICE_IP/32  # Your ISP public IP + /32

# Or allow from Azure ISISvoice (if you know the IP)
# --source-security-group sg-isisvoice
```

#### For Ollama SG

```bash
aws ec2 authorize-security-group-ingress \
  --group-id sg-ollama \
  --protocol tcp \
  --port 11434 \
  --cidr YOUR_OFFICE_IP/32
```

**⚠️ Security Note**: Restrict access to your specific IP or Azure ISISvoice security group. Do NOT allow `0.0.0.0/0` for production.

---

### 4. Test End-to-End

```bash
# From your local machine or Azure ISISvoice

# Test Whisper transcription
curl -X POST http://WHISPER_IP:8001/transcribe \
  -H "Content-Type: application/json" \
  -d '{
    "audio_base64": "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA//NJZAAAAAQAAABQAAAAAFmAAEg==",
    "language": "es",
    "file_name": "test.wav"
  }'

# Test Ollama inference
curl -X POST http://OLLAMA_IP:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "medical3.1",
    "prompt": "El paciente tiene fiebre de 39°C",
    "stream": false
  }'
```

---

## Monitoring and Maintenance

### Monitor Logs

```bash
# Whisper logs
sudo tail -f /var/log/whisper.log

# Ollama logs
sudo journalctl -u ollama -f
```

### Set Up CloudWatch Alarms

```bash
# High CPU usage
aws cloudwatch put-metric-alarm \
  --alarm-name whisper-high-cpu \
  --alarm-description "Alert when Whisper CPU > 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2

# High memory usage (requires CloudWatch agent)
# See: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Install-CloudWatch-Agent.html
```

### Scale Down During Off-Hours

```bash
# Stop instances when not needed (preserves data)
aws ec2 stop-instances --instance-ids i-whisper i-ollama

# Restart when needed
aws ec2 start-instances --instance-ids i-whisper i-ollama

# Or use AWS Lambda + EventBridge for scheduled on/off
```

---

## Troubleshooting

### Whisper not responding on port 8001

```bash
ssh -i your-key.pem ubuntu@WHISPER_IP

# Check if process is running
ps aux | grep whisper

# Check listening ports
sudo netstat -tlnp | grep 8001

# Restart service
sudo systemctl restart whisper

# Check logs
sudo journalctl -u whisper -n 50
```

### Ollama model not loaded

```bash
ssh -i your-key.pem ubuntu@OLLAMA_IP

# Check model status
ollama list

# If not there, pull again
ollama pull medical3.1

# Monitor progress
tail -f /var/log/ollama-pull.log
```

### High latency from Azure

- Check network latency: `ping WHISPER_IP` from Azure ISISvoice
- Consider moving instances to same region as Azure (e.g., us-east-1)
- Check AWS security groups aren't blocking traffic

---

## Cost Optimization

### Shutdown Strategy

- **Development**: Stop instances when not in use
- **Production**: Use CloudWatch + Lambda for scheduled shutdown during off-hours

### Instance Right-Sizing

After initial deployment, monitor actual usage:

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 \
  --metric-name CPUUtilization \
  --dimensions Name=InstanceId,Value=i-whisper \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-30T00:00:00Z \
  --period 86400 \
  --statistics Average
```

If average CPU < 20%, consider smaller instance type.

---

## Next Steps

1. Record your static IPs:
   - Whisper: `http://WHISPER_IP:8001`
   - Ollama: `http://OLLAMA_IP:11434`

2. Update `terraform/terraform.tfvars` with these IPs

3. Deploy ISISvoice on Azure using Terraform (see `terraform/README.md`)

4. Test end-to-end connectivity

---

## Support & References

- Whisper Documentation: https://github.com/openai/whisper
- Ollama Documentation: https://github.com/ollama/ollama
- AWS EC2: https://docs.aws.amazon.com/ec2/
- FastAPI: https://fastapi.tiangolo.com/
