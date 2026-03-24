#!/bin/bash
# Voice Service startup script

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}════════════════════════════════════════${NC}"
echo -e "${BLUE}  Voice Service - Startup Script${NC}"
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo

echo -e "${YELLOW}Detecting Python...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo -e "${RED}Python not found. Please install Python 3.8+${NC}"
    exit 1
fi

PYTHON_VERSION=$($PYTHON --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}Python $PYTHON_VERSION found${NC}"
echo

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

# Cargar variables de entorno desde .env si existe.
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.env"
    set +a
fi

if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    $PYTHON -m venv "$VENV_DIR"
    echo -e "${GREEN}Virtual environment created${NC}"
fi

echo -e "${YELLOW}Activating virtual environment...${NC}"
source "$VENV_DIR/bin/activate" || . "$VENV_DIR/Scripts/activate"
echo -e "${GREEN}Virtual environment activated${NC}"
echo

echo -e "${YELLOW}Installing dependencies...${NC}"
if [ -f "$PROJECT_DIR/src/app/requirements.txt" ]; then
    pip install -q -r "$PROJECT_DIR/src/app/requirements.txt"
    echo -e "${GREEN}Dependencies installed${NC}"
else
    echo -e "${RED}requirements.txt not found${NC}"
    exit 1
fi
echo

echo -e "${YELLOW}Verifying Whisper model...${NC}"
$PYTHON -c "import whisper; whisper.load_model('tiny')" 2>/dev/null
echo -e "${GREEN}Whisper model ready${NC}"
echo

echo -e "${BLUE}════════════════════════════════════════${NC}"
echo -e "${GREEN}Starting FastAPI server...${NC}"
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo

echo -e "${YELLOW}Checking port 8000 availability...${NC}"
if ss -ltn 2>/dev/null | grep -q ':8000 '; then
    echo -e "${RED}Port 8000 is already in use.${NC}"
    echo -e "${YELLOW}Process using port 8000:${NC}"
    ss -ltnp 2>/dev/null | grep ':8000' || true
    echo
    echo -e "${YELLOW}Stop the running server first, then retry:${NC}"
    echo "  pkill -f 'uvicorn app.main:app'"
    exit 1
fi
echo -e "${GREEN}Port 8000 is free${NC}"
echo

echo "API available at:"
echo "  http://localhost:8000"
echo "  http://localhost:8000/docs (documentation)"
echo "  POST /speech/transcribe-file"
echo "  POST /speech/ia/analyze"
echo "  POST /speech/flow/audio"
echo
echo "Web client:"
echo "  http://localhost:8000/client.html"
echo "  (optional fallback: file://$PROJECT_DIR/client.html)"
echo
echo "Dependencies:"
echo "  OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://localhost:11434}"
echo "  OLLAMA_MODEL=${OLLAMA_MODEL:-medical3.1}"
if [ -n "${MONGODB_URI:-}" ]; then
    echo "  MONGODB_URI=set"
else
    echo "  MONGODB_URI=mongodb://localhost:27017"
fi
echo
echo "Press Ctrl+C to stop"
echo

cd "$PROJECT_DIR/src"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
