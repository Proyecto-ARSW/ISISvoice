# ISISvoice - Quick Start (5 Min Overview)

## 🎯 En Una Línea
ISISvoice ahora corre en **Azure (API)** + **AWS (Modelos)** con variables de entorno para conectarlos.

---

## ⚡ Pasos Rápidos (Sin Detalles)

### AWS Setup (30 min)

```bash
# 1. Crear 2 EC2 instances (Ubuntu 22.04)
#    Instance 1: t3.medium → Whisper (port 8001)
#    Instance 2: t3.xlarge → Ollama (port 11434)

# 2. Asignar Elastic IPs

# 3. SSH a Whisper:
ssh -i key.pem ubuntu@WHISPER_IP
wget https://raw.githubusercontent.com/tu-repo/aws-servers/install-whisper.sh
chmod +x install-whisper.sh && ./install-whisper.sh

# 4. SSH a Ollama:
ssh -i key.pem ubuntu@OLLAMA_IP
wget https://raw.githubusercontent.com/tu-repo/aws-servers/install-ollama.sh
chmod +x install-ollama.sh && ./install-ollama.sh
# ← Esperar que cargue modelo (nohup ollama pull medical3.1)

# 5. Anotar IPs:
WHISPER_IP=_______________
OLLAMA_IP=_______________
```

### Azure Setup (20 min)

```bash
# 1. Construir imagen
docker build -t isisvoice:latest -f src/app/Dockerfile .

# 2. Push a ACR
az acr build --registry isisvoiceacr --image isisvoice:latest -f src/app/Dockerfile .

# 3. Terraform
cd terraform/
cp terraform.tfvars.example terraform.tfvars
# ↓ EDITAR terraform.tfvars:
# isisvoice_image = "isisvoiceacr.azurecr.io/isisvoice:latest"
# whisper_api_url = "http://WHISPER_IP:8001"
# ollama_base_url = "http://OLLAMA_IP:11434"

terraform init
terraform apply
# ← Anotar URL de salida
```

### Test (5 min)

```bash
# Test Whisper
curl http://WHISPER_IP:8001/health

# Test Ollama
curl http://OLLAMA_IP:11434/api/tags

# Test ISISvoice
curl https://YOUR_AZURE_URL/speech/health
```

---

## 📋 Variables a Actualizar

**Editar `.env` o `terraform.tfvars` con tus valores:**

```env
WHISPER_API_URL=http://WHISPER_IP:8001
OLLAMA_BASE_URL=http://OLLAMA_IP:11434
MONGODB_URI=mongodb+srv://...
JWT_SECRET=...
```

---

## 📊 Costos

| Servicio | Costo/Mes |
|----------|-----------|
| Azure (ISISvoice) | $5-15 |
| AWS Whisper | $25-30 |
| AWS Ollama | $130-150 |
| **TOTAL** | **$160-195** |

*Si reduces horas: $50-80/mes*

---

## 🔗 Archivos Clave

- 📖 Guía Completa: `README_DEPLOYMENT.md`
- 📖 Resumen Ejecutivo: `INSTALLATION_SUMMARY.md`
- 📖 Guía AWS: `AWS_DEPLOYMENT_GUIDE.md`
- 📖 Guía Terraform: `terraform/README.md`
- 🐍 Código Whisper: `aws-servers/whisper_server.py`
- 🔧 Script Automático: `DEPLOYMENT_GUIDE.sh`

---

## ✅ Checklist Mínimo

```
[ ] AWS Whisper respondiendo en puerto 8001
[ ] AWS Ollama respondiendo en puerto 11434
[ ] Azure Container Registry tiene imagen
[ ] Terraform.tfvars completado con IPs
[ ] terraform apply exitoso
[ ] ISISvoice responde en Azure
```

---

## ❓ Si Algo Falla

| Problema | Solución |
|----------|----------|
| Whisper no responde | `journalctl -u whisper -f` en la máquina |
| Ollama no responde | `sudo systemctl status ollama` |
| ISISvoice no conecta | Verificar IPs en terraform.tfvars |
| Docker build falla | Verificar src/app/Dockerfile existe |
| Terraform error | Verificar terraform.tfvars tiene valores correctos |

Ver `AWS_DEPLOYMENT_GUIDE.md` → Troubleshooting para soluciones detalladas.

---

## 🎓 ¿Por Qué Estos Cambios?

✅ **Dockerfile 87% más pequeño** (4GB → 500MB)  
✅ **Arranque 3x más rápido** (3min → <1min)  
✅ **Costo Azure reducido drasticamente** (encaja en presupuesto)  
✅ **Escalable** (puede crecer sin problemas)  
✅ **Flexible** (cambiar IPs sin redeploy)  

---

**Listo? Empieza por AWS, luego Azure. ¡Buena suerte! 🚀**
