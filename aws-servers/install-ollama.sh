#!/bin/bash

# Ollama Server Installation Script for AWS EC2
# Run this on Ubuntu 22.04 LTS EC2 instance
# Usage: chmod +x install-ollama.sh && ./install-ollama.sh

set -e

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║       Ollama Server Installation for AWS EC2                  ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Update system
echo "[1/4] Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install Ollama
echo "[2/4] Installing Ollama..."
curl -fsSL https://ollama.ai/install.sh | sh

# Enable and start service
echo "[3/4] Starting Ollama service..."
sudo systemctl enable ollama
sudo systemctl start ollama

# Wait for service
sleep 5

echo "[4/4] Pulling medical model (this may take 10-30 minutes)..."
echo "Run this in background or in a tmux session:"
echo ""
echo "  tmux new-session -d -s ollama 'ollama pull medical3.1'"
echo "  tmux attach -t ollama"
echo ""
echo "Or with nohup:"
echo ""
echo "  nohup ollama pull medical3.1 > /var/log/ollama-pull.log 2>&1 &"
echo "  tail -f /var/log/ollama-pull.log"
echo ""

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                   INSTALLATION COMPLETE                       ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "Service Status:"
sudo systemctl status ollama

echo ""
echo "Testing health endpoint:"
curl http://localhost:11434/api/tags || echo "Service not yet ready"

echo ""
echo "✓ Ollama installed and running on port 11434"
echo ""
echo "Next steps:"
echo "1. Pull a model: ollama pull medical3.1 (in background/tmux)"
echo "2. Monitor: tail -f /var/log/ollama-pull.log"
echo "3. Test endpoint: curl http://INSTANCE_IP:11434/api/tags"
echo ""
