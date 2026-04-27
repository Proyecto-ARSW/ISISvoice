#!/bin/bash

# ISISvoice AWS Setup - Whisper + Ollama en misma EC2
# Compatible con Ubuntu y Amazon Linux

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

SUDO_USER_NAME="${SUDO_USER:-ec2-user}"
WHISPER_IMAGE="${WHISPER_IMAGE:-}"

require_whisper_image() {
  if [ -z "$WHISPER_IMAGE" ]; then
    echo -e "${RED}WHISPER_IMAGE is required for remote deploy.${NC}"
    echo "Example:"
    echo "  export WHISPER_IMAGE=ghcr.io/<owner>/isisvoice-whisper:cpu-latest"
    exit 1
  fi
}

install_packages_ubuntu() {
  apt-get update && apt-get upgrade -y
  apt-get install -y ca-certificates curl gnupg git ffmpeg
}

install_packages_amazon() {
  # Avoid dnf/yum system-wide upgrade here: on Amazon Linux 2023 it can try to
  # replace curl-minimal with curl and fail due to conflicting packages.
  if ! command -v git >/dev/null 2>&1; then
    if command -v dnf >/dev/null 2>&1; then
      dnf install -y git --allowerasing
    else
      yum install -y git
    fi
  fi

  echo -e "${YELLOW}curl no se reinstala en el host Amazon Linux para evitar conflicto con curl-minimal.${NC}"
  echo -e "${YELLOW}ffmpeg no se instala en el host Amazon Linux; el contenedor Whisper ya lo incluye.${NC}"
}

install_docker_ubuntu() {
  if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
  fi

  if ! docker compose version >/dev/null 2>&1; then
    apt-get update
    apt-get install -y docker-compose-plugin
  fi
}

install_docker_amazon() {
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y docker
  else
    if command -v amazon-linux-extras >/dev/null 2>&1; then
      amazon-linux-extras install docker -y
    fi
    yum install -y docker
  fi

  systemctl enable docker
  systemctl start docker
}

install_compose_binary() {
  local arch
  arch=$(uname -m)
  case "$arch" in
    x86_64) arch="x86_64" ;;
    aarch64 | arm64) arch="aarch64" ;;
    *) arch="x86_64" ;;
  esac

  local compose_version="v2.32.4"
  local target_dir="/usr/local/lib/docker/cli-plugins"
  local target_file="$target_dir/docker-compose"

  mkdir -p "$target_dir"
  curl -L "https://github.com/docker/compose/releases/download/${compose_version}/docker-compose-linux-${arch}" -o "$target_file"
  chmod +x "$target_file"
  ln -sf "$target_file" /usr/local/bin/docker-compose
}

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
  else
    echo "docker-compose"
  fi
}

compose_exec() {
  local cmd
  cmd=$(compose_cmd)
  $cmd "$@"
}

ensure_directory() {
  mkdir -p /opt/isisvoice/models/{whisper,ollama}
  chown -R "$SUDO_USER_NAME":"$SUDO_USER_NAME" /opt/isisvoice 2>/dev/null || true
}

# Step 1: Update system
echo -e "${YELLOW}[1/6] Updating system...${NC}"
if [ -f /etc/os-release ] && grep -qiE 'amzn|amazon' /etc/os-release; then
  install_packages_amazon
  OS_FAMILY="amazon"
else
  install_packages_ubuntu
  OS_FAMILY="ubuntu"
fi
echo -e "${GREEN}✓ System updated${NC}"
echo ""

# Step 2: Install Docker
echo -e "${YELLOW}[2/6] Installing Docker...${NC}"
if ! command -v docker &> /dev/null; then
  if [ "$OS_FAMILY" = "amazon" ]; then
    install_docker_amazon
  else
    install_docker_ubuntu
  fi

  if id "$SUDO_USER_NAME" >/dev/null 2>&1; then
    usermod -aG docker "$SUDO_USER_NAME" || true
  fi
  echo -e "${GREEN}✓ Docker installed${NC}"
else
  echo -e "${GREEN}✓ Docker already installed${NC}"
fi
echo ""

# Step 3: Install Docker Compose
echo -e "${YELLOW}[3/6] Installing Docker Compose...${NC}"
if docker compose version &> /dev/null; then
  echo -e "${GREEN}✓ Docker Compose plugin already installed${NC}"
else
  if [ "$OS_FAMILY" = "amazon" ]; then
    install_compose_binary
  else
    apt-get update
    apt-get install -y docker-compose-plugin
  fi

  if docker compose version &> /dev/null; then
    echo -e "${GREEN}✓ Docker Compose installed${NC}"
  else
    echo -e "${YELLOW}Docker Compose plugin not available, using docker-compose if present.${NC}"
  fi
fi
echo ""

# Step 4: Create directories
echo -e "${YELLOW}[4/6] Creating directory structure...${NC}"
ensure_directory
cd /opt/isisvoice
echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# Step 5: Download docker-compose.yml
echo -e "${YELLOW}[5/6] Downloading Docker Compose configuration...${NC}"
cat > docker-compose.yml << 'EOF'
services:
  whisper:
    image: ${WHISPER_IMAGE}
    container_name: whisper
    ports:
      - "8001:8001"
    environment:
      - WHISPER_MODEL=small
      - WHISPER_COMPUTE_TYPE=int8
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

# Step 6: Pull Whisper image
echo -e "${YELLOW}[6/6] Pulling Whisper image...${NC}"
require_whisper_image
docker pull "$WHISPER_IMAGE"
echo -e "${GREEN}✓ Whisper image downloaded (${WHISPER_IMAGE})${NC}"
echo ""

# Start services
echo -e "${YELLOW}Starting services...${NC}"
COMPOSE_CMD=$(compose_cmd)
$COMPOSE_CMD up -d

# Step 8: Pull Ollama model
echo -e "${YELLOW}Pulling Ollama model (medgemma:4b)...${NC}"
if $COMPOSE_CMD ps ollama >/dev/null 2>&1; then
  $COMPOSE_CMD exec -T ollama ollama pull medgemma:4b &
else
  echo -e "${YELLOW}Ollama container not ready yet; pull it manually with:${NC}"
  echo "  $COMPOSE_CMD exec -T ollama ollama pull medgemma:4b"
fi

# Wait for services to start
echo -e "${YELLOW}Waiting for services to initialize...${NC}"
sleep 30

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
curl -s http://localhost:11434/api/tags | grep -q "medgemma:4b" && echo -e "${GREEN}✓ Ollama OK${NC}" || echo -e "${YELLOW}⏳ Ollama loading model...${NC}"

echo ""
echo "📝 Logs:"
echo "  Whisper: $COMPOSE_CMD logs -f whisper"
echo "  Ollama: $COMPOSE_CMD logs -f ollama"
echo ""
echo "🛑 To stop services: $COMPOSE_CMD down"
echo "🔄 To restart: $COMPOSE_CMD restart"
echo ""
echo "Working directory: /opt/isisvoice"
echo ""
