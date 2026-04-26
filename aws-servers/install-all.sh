#!/bin/bash

# ISISvoice AWS Setup - Whisper + Ollama en misma EC2
# Ejecutar en Ubuntu 22.04 LTS

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║    ISISvoice AWS Setup - Whisper + Ollama (Docker)         ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then 
  echo -e "${RED}Please run with sudo${NC}"
  exit 1
fi

# Step 1: Update system
echo -e "${YELLOW}[1/6] Updating system...${NC}"
apt-get update && apt-get upgrade -y
echo -e "${GREEN}✓ System updated${NC}"
echo ""

# Step 2: Install Docker
echo -e "${YELLOW}[2/6] Installing Docker...${NC}"
if ! command -v docker &> /dev/null; then
  curl -fsSL https://get.docker.com -o get-docker.sh
  sh get-docker.sh
  usermod -aG docker ubuntu
  echo -e "${GREEN}✓ Docker installed${NC}"
else
  echo -e "${GREEN}✓ Docker already installed${NC}"
fi
echo ""

# Step 3: Install Docker Compose
echo -e "${YELLOW}[3/6] Installing Docker Compose...${NC}"
if ! command -v docker-compose &> /dev/null; then
  curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
  chmod +x /usr/local/bin/docker-compose
  echo -e "${GREEN}✓ Docker Compose installed${NC}"
else
  echo -e "${GREEN}✓ Docker Compose already installed${NC}"
fi
echo ""

# Step 4: Create directories
echo -e "${YELLOW}[4/6] Creating directory structure...${NC}"
mkdir -p /opt/isisvoice/models/{whisper,ollama}
cd /opt/isisvoice
echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# Step 5: Download docker-compose.yml
echo -e "${YELLOW}[5/6] Downloading Docker Compose configuration...${NC}"
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  whisper:
    image: whisper-api:latest
    build:
      context: .
      dockerfile: Dockerfile.whisper
    container_name: whisper
    ports:
      - "8001:8001"
    environment:
      - WHISPER_MODEL=large-v3
      - PORT=8001
      - HOST=0.0.0.0
    volumes:
      - ./models/whisper:/root/.cache/whisper
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
    networks:
      - isisvoice

  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    ports:
      - "11434:11434"
    environment:
      - OLLAMA_MODELS=/data/ollama/models
      - OLLAMA_NUM_GPU=0
    volumes:
      - ./models/ollama:/data/ollama/models
      - ollama-data:/root/.ollama
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    networks:
      - isisvoice

networks:
  isisvoice:
    driver: bridge

volumes:
  ollama-data:
    driver: local
EOF
echo -e "${GREEN}✓ Configuration downloaded${NC}"
echo ""

# Step 6: Download Dockerfile.whisper
echo -e "${YELLOW}[6/6] Downloading Dockerfile for Whisper...${NC}"
cat > Dockerfile.whisper << 'EOF'
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    openai-whisper \
    fastapi uvicorn[standard] \
    python-multipart pydantic

RUN cat > /app/server.py << 'PYEOF'
import base64, logging, tempfile, os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import whisper, uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Whisper API", version="1.0")

MODEL_SIZE = os.getenv("WHISPER_MODEL", "large-v3")
model = None

class TranscriptionRequest(BaseModel):
    audio_base64: str
    language: str = "es"
    file_name: str = "audio.wav"

@app.on_event("startup")
async def startup_event():
    global model
    logger.info(f"Loading Whisper model: {MODEL_SIZE}")
    model = whisper.load_model(MODEL_SIZE)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "whisper-api", "model": MODEL_SIZE, "version": "1.0"}

@app.post("/transcribe")
async def transcribe(request: TranscriptionRequest):
    if not model:
        raise HTTPException(status_code=503, detail="Model not loaded")
    if not request.audio_base64:
        raise HTTPException(status_code=400, detail="No audio data")
    
    temp_path = None
    try:
        audio_bytes = base64.b64decode(request.audio_base64)
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp.write(audio_bytes)
            temp_path = tmp.name
        result = model.transcribe(temp_path, language=request.language, verbose=False, fp16=False)
        return {"transcription": result.get('text', '').strip(), "language": request.language, "model": MODEL_SIZE}
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port, workers=1)
PYEOF

EXPOSE 8001
CMD ["python", "/app/server.py"]
EOF
echo -e "${GREEN}✓ Dockerfile created${NC}"
echo ""

# Step 7: Build and start services
echo -e "${YELLOW}Building and starting services...${NC}"
docker-compose build
docker-compose up -d

# Wait for services to start
echo -e "${YELLOW}Waiting for services to initialize...${NC}"
sleep 30

# Step 8: Pull Ollama model
echo -e "${YELLOW}Pulling Ollama model (medical3.1)...${NC}"
docker-compose exec -T ollama ollama pull medical3.1 &

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║              INSTALLATION COMPLETE                         ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

echo -e "${GREEN}✓ Whisper API: http://localhost:8001${NC}"
echo -e "${GREEN}✓ Ollama API: http://localhost:11434${NC}"
echo ""

echo -e "${YELLOW}Testing services...${NC}"
curl -s http://localhost:8001/health && echo -e "${GREEN}✓ Whisper OK${NC}" || echo -e "${RED}✗ Whisper not ready yet${NC}"
curl -s http://localhost:11434/api/tags | grep -q "medical3.1" && echo -e "${GREEN}✓ Ollama OK${NC}" || echo -e "${YELLOW}⏳ Ollama loading model...${NC}"

echo ""
echo "📝 Logs:"
echo "  Whisper: docker logs -f whisper"
echo "  Ollama: docker logs -f ollama"
echo ""
echo "🛑 To stop services: docker-compose down"
echo "🔄 To restart: docker-compose restart"
echo ""
echo "Working directory: /opt/isisvoice"
echo ""
