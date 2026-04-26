# AWS Servers Setup

This directory contains scripts and code for deploying Whisper and Ollama on AWS EC2 instances.

## Files

- **whisper_server.py**: FastAPI server for Whisper transcription (runs on port 8001)
- **install-whisper.sh**: Automated installation script for Whisper server
- **install-ollama.sh**: Automated installation script for Ollama

## Quick Start

### Whisper Server (Port 8001)

```bash
# On your AWS EC2 instance (Ubuntu 22.04)
chmod +x install-whisper.sh
./install-whisper.sh

# Monitor startup
journalctl -u whisper -f
```

### Ollama Server (Port 11434)

```bash
# On your AWS EC2 instance (Ubuntu 22.04)
chmod +x install-ollama.sh
./install-ollama.sh

# Pull model in background
nohup ollama pull medical3.1 > /var/log/ollama-pull.log 2>&1 &
```

## Environment Variables

### Whisper Server

- `WHISPER_MODEL`: Model size (default: `large-v3`)
  - Options: `tiny`, `base`, `small`, `medium`, `large`, `large-v3`
- `PORT`: Server port (default: `8001`)
- `HOST`: Server host (default: `0.0.0.0`)

### Ollama Server

- `OLLAMA_NUM_GPU`: Number of GPUs to use (default: auto-detect)
- `OLLAMA_MODELS`: Path to model storage (default: `/usr/share/ollama/.ollama/models`)

## API Endpoints

### Whisper

```bash
# Health check
GET /health

# Transcribe base64-encoded audio
POST /transcribe
{
  "audio_base64": "...",
  "language": "es",
  "file_name": "audio.wav"
}

# Transcribe multipart file upload
POST /transcribe-multipart
# with file and language parameters
```

### Ollama

```bash
# List models
GET /api/tags

# Generate completion
POST /api/generate
{
  "model": "medical3.1",
  "prompt": "Patient symptoms...",
  "stream": false
}

# Chat endpoint
POST /api/chat
{
  "model": "medical3.1",
  "messages": [...],
  "stream": false
}
```

## Cost Notes

- **Whisper**: t3.medium (~$25/month) or t3a.large (~$35/month)
- **Ollama**: t3.xlarge (~$150/month) or g4dn.xlarge with GPU (~$500/month)

To reduce costs:
- Stop instances when not in use
- Use scheduled scaling
- Use smaller instance types after verifying performance

## See Also

- [AWS_DEPLOYMENT_GUIDE.md](../AWS_DEPLOYMENT_GUIDE.md) for detailed setup
- [terraform/README.md](../terraform/README.md) for Azure deployment
- [DEPLOYMENT_GUIDE.sh](../DEPLOYMENT_GUIDE.sh) for end-to-end workflow
