# ISISvoice - Setup & Deployment Guide

Guía completa para desplegar, orquestar y probar ISISvoice en Azure + AWS (con Whisper + Ollama en misma EC2).

## 📋 Tabla de Contenidos

1. [Arquitectura](#arquitectura)
2. [Requisitos Previos](#requisitos-previos)
3. [Paso 1: Desplegar en AWS](#paso-1-desplegar-en-aws)
4. [Paso 2: Desplegar en Azure](#paso-2-desplegar-en-azure)
5. [Paso 3: Testing y Validación](#paso-3-testing-y-validación)
6. [Troubleshooting](#troubleshooting)

---

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────┐
│              Azure (Tu Cuenta)                  │
│  ┌──────────────────────────────────────────┐   │
│  │  Container Apps - ISISvoice API          │   │
│  │  • FastAPI server                        │   │
│  │  • Scale-to-zero                         │   │
│  │  • Puertos: 8000                         │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
                      │
                      │ HTTP calls
                      │
┌─────────────────────────────────────────────────┐
│              AWS (Tu Cuenta)                    │
│  ┌──────────────────────────────────────────┐   │
│  │  EC2 t3.xlarge (Ubuntu 22.04)            │   │
│  │  ┌─────────────┐  ┌──────────────────┐  │   │
│  │  │  Whisper    │  │  Ollama          │  │   │
│  │  │  :8001      │  │  :11434          │  │   │
│  │  │  ASR        │  │  Medical Model   │  │   │
│  │  └─────────────┘  └──────────────────┘  │   │
│  │  Elastic IP: static                     │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
                      │
┌─────────────────────────────────────────────────┐
│         MongoDB Atlas (Tu Cuenta)               │
│  • Historiales de pacientes                     │
│  • Sesiones clínicas                            │
└─────────────────────────────────────────────────┘
```

**Ventaja**: Whisper + Ollama en misma VM = costo reducido, orquestación simple

---

## 📋 Requisitos Previos

### Cuentas Necesarias
- ✅ AWS Account (activo, con créditos)
- ✅ Azure Account (con beneficios de estudiante)
- ✅ MongoDB Atlas (cluster configurado)

### Software Local
- ✅ Git
- ✅ Docker
- ✅ Terraform >= 1.0
- ✅ Azure CLI
- ✅ AWS CLI (opcional pero recomendado)
- ✅ SSH client

### Datos a Anotar
Antes de empezar, prepara:
- [ ] **MongoDB URI**: `mongodb+srv://user:pass@cluster.mongodb.net`
- [ ] **MongoDB DB**: `voice_medical`
- [ ] **JWT Secret**: Tu clave secreta
- [ ] **AWS Key Pair**: Para SSH a instancia EC2

---

## 🚀 Paso 1: Desplegar en AWS

### 1.1 Crear Instancia EC2

**Vía AWS Console**:
1. EC2 Dashboard → Launch Instance
2. **AMI**: Ubuntu 22.04 LTS
3. **Instance Type**: `t3.xlarge` (4 vCPU, 16GB RAM)
4. **Storage**: 50GB gp3
5. **Security Group**: 
   - Inbound: 8001 (Whisper), 11434 (Ollama), 22 (SSH)
   - Source: Tu IP / 0.0.0.0/0 (temporal para testing)
6. **Key Pair**: Selecciona o crea una
7. Launch

**Vía AWS CLI**:
```bash
aws ec2 run-instances \
  --image-ids ami-0c55b159cbfafe1f0 \
  --instance-type t3.xlarge \
  --key-name tu-key-pair \
  --security-groups whisper-ollama-sg \
  --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=50,VolumeType=gp3}" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=whisper-ollama}]"
```

### 1.2 Asignar Elastic IP (Static IP)

```bash
# Allocate new Elastic IP
aws ec2 allocate-address --domain vpc
# Output: AllocationId: eipalloc-xxxxxxx, PublicIp: 54.123.45.67

# Associate with EC2 instance
aws ec2 associate-address \
  --allocation-id eipalloc-xxxxxxx \
  --instance-id i-xxxxxxx
```

**Anotar**: `AWS_EC2_IP = _______________` (ej: 54.123.45.67)

### 1.3 Conectar y Descargar Scripts

```bash
# SSH a instancia
ssh -i tu-key.pem ubuntu@AWS_EC2_IP

# Clonar repo (o descargar archivos manualmente)
git clone https://github.com/tu-repo/ISISvoice.git
cd ISISvoice/aws-servers

# Ver archivos disponibles
ls -la
# Debes ver: docker-compose.yml, install-all.sh, README.md
```

### 1.4 Ejecutar Instalación (Whisper + Ollama en mismo Docker)

```bash
# Hacer script ejecutable
chmod +x install-all.sh

# Ejecutar instalación
./install-all.sh

# Monitorear progreso
docker logs -f whisper &
docker logs -f ollama &
```

**Qué hace el script**:
- ✅ Instala Docker y Docker Compose
- ✅ Construye e inicia contenedor Whisper (puerto 8001)
- ✅ Inicia contenedor Ollama (puerto 11434)
- ✅ Descarga modelo medical3.1 (toma ~20-30 min)
- ✅ Configura auto-restart

### 1.5 Validar Servicios

```bash
# Dentro de la instancia
curl http://localhost:8001/health
# Respuesta: {"status":"healthy","service":"whisper-api",...}

curl http://localhost:11434/api/tags
# Respuesta: {"models":[{"name":"medical3.1:latest",...}]}

# Desde tu máquina local
curl http://AWS_EC2_IP:8001/health
curl http://AWS_EC2_IP:11434/api/tags
```

✅ **AWS listo**. Anotar:
- `WHISPER_API_URL = http://AWS_EC2_IP:8001`
- `OLLAMA_BASE_URL = http://AWS_EC2_IP:11434`

---

## ☁️ Paso 2: Desplegar en Azure

### 2.1 Preparar Imagen Docker

```bash
# En tu máquina local, en carpeta del proyecto
docker build -t isisvoice:latest -f src/app/Dockerfile .

# Verificar imagen
docker images | grep isisvoice
```

### 2.2 Crear Azure Container Registry (ACR)

```bash
# Login a Azure
az login
az account set --subscription "YOUR_SUBSCRIPTION_ID"

# Crear ACR (nombre único)
az acr create \
  --resource-group rg-isisvoice \
  --name isisvoiceacr \
  --sku Basic

# Build y push imagen en un paso
az acr build \
  --registry isisvoiceacr \
  --image isisvoice:latest \
  -f src/app/Dockerfile .

# Verificar
az acr repository list --name isisvoiceacr
```

### 2.3 Configurar Terraform

```bash
cd terraform/

# Copiar plantilla
cp terraform.tfvars.example terraform.tfvars

# Editar terraform.tfvars con tus valores:
nano terraform.tfvars  # o tu editor favorito
```

**Valores a configurar**:
```hcl
location                = "eastus"
resource_group_name     = "rg-isisvoice"
container_registry_name = "isisvoiceacr"

# Imagen
isisvoice_image = "isisvoiceacr.azurecr.io/isisvoice:latest"

# AWS endpoints (anotar del paso anterior)
whisper_api_url = "http://AWS_EC2_IP:8001"
ollama_base_url = "http://AWS_EC2_IP:11434"

# MongoDB (tu URI existente)
mongodb_uri = "mongodb+srv://user:pass@cluster.mongodb.net/?appName=SITI"
mongodb_db  = "voice_medical"

# JWT (tu secret)
jwt_secret = "your-secret-key"

# Scaling
min_replicas = 0  # Scale to zero (ahorrar costos)
max_replicas = 3
```

### 2.4 Desplegar con Terraform

```bash
# Inicializar
terraform init

# Validar
terraform validate

# Plan
terraform plan

# Apply
terraform apply

# Esperar 2-3 minutos...
```

**Anotar salida**:
```
Outputs:
isisvoice_url = "https://isisvoice-production.azuremanageddata.com"
container_registry_url = "isisvoiceacr.azurecr.io"
```

### 2.5 Verificar Despliegue

```bash
# Test ISISvoice en Azure
curl https://YOUR_AZURE_URL/speech/health

# Debes ver respuesta exitosa
```

✅ **Azure listo**. Anotar:
- `AZURE_URL = https://YOUR_AZURE_URL`

---

## 🧪 Paso 3: Testing y Validación

### 3.1 Test de Conectividad

```bash
# 1. Test Whisper
echo "Testing Whisper..."
curl http://AWS_EC2_IP:8001/health

# 2. Test Ollama
echo "Testing Ollama..."
curl http://AWS_EC2_IP:11434/api/tags

# 3. Test ISISvoice Azure
echo "Testing ISISvoice..."
curl https://YOUR_AZURE_URL/speech/health

# Todos deberían responder con estatus 200
```

### 3.2 Test de Transcripción

```bash
# Crear archivo de audio (o usar uno existente)
# Guardar como: test-audio.wav

# Convertir a base64
AUDIO_B64=$(base64 -w 0 test-audio.wav)

# Llamar endpoint Whisper
curl -X POST http://AWS_EC2_IP:8001/transcribe \
  -H "Content-Type: application/json" \
  -d '{
    "audio_base64": "'$AUDIO_B64'",
    "language": "es",
    "file_name": "test.wav"
  }'

# Respuesta esperada:
# {"transcription": "el paciente tiene fiebre", "language": "es", "model": "large-v3"}
```

### 3.3 Test de Inferencia Ollama

```bash
# Test modelo cargado
curl -X POST http://AWS_EC2_IP:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "medical3.1",
    "prompt": "Paciente presenta fiebre de 39°C",
    "stream": false
  }'

# Respuesta esperada:
# {"model": "medical3.1", "response": "La fiebre moderada puede indicar...", ...}
```

### 3.4 Test del Flujo Completo

```bash
# 1. Obtener JWT token (si requiere autenticación)
TOKEN="your-jwt-token"

# 2. Llamar triage endpoint en Azure
curl -X POST https://YOUR_AZURE_URL/triage/process \
  -H "Authorization: Bearer $TOKEN" \
  -F "audio=@test-audio.wav" \
  -F "patient_id=test-patient"

# 3. Verificar respuesta
# Debes ver triage_level, symptoms, vital_signs, etc.
```

### 3.5 Script de Testing Automatizado

```bash
#!/bin/bash

AWS_IP="YOUR_AWS_IP"
AZURE_URL="YOUR_AZURE_URL"

echo "🧪 ISISvoice Health Check"
echo "=========================="
echo ""

echo "1. Testing Whisper (AWS)..."
whisper_health=$(curl -s http://$AWS_IP:8001/health)
if echo $whisper_health | grep -q "healthy"; then
  echo "✅ Whisper: OK"
else
  echo "❌ Whisper: FAILED"
fi

echo ""
echo "2. Testing Ollama (AWS)..."
ollama_health=$(curl -s http://$AWS_IP:11434/api/tags)
if echo $ollama_health | grep -q "medical3.1"; then
  echo "✅ Ollama: OK"
else
  echo "❌ Ollama: FAILED"
fi

echo ""
echo "3. Testing ISISvoice (Azure)..."
isisvoice_health=$(curl -s https://$AZURE_URL/speech/health)
if echo $isisvoice_health | grep -q "healthy"; then
  echo "✅ ISISvoice: OK"
else
  echo "❌ ISISvoice: FAILED"
fi

echo ""
echo "=========================="
echo "All systems check complete!"
```

---

## 🔧 Orquestación y Mantenimiento

### Monitoreo en Tiempo Real

**Whisper (AWS)**:
```bash
ssh -i tu-key.pem ubuntu@AWS_EC2_IP
docker logs -f whisper
```

**Ollama (AWS)**:
```bash
docker logs -f ollama
```

**ISISvoice (Azure)**:
```bash
az containerapp logs show \
  --name isisvoice-production \
  --resource-group rg-isisvoice
```

### Actualizar Código

**ISISvoice**:
```bash
# Modificar código localmente
git commit -am "Update API code"
git push

# Rebuildar y pushear imagen
docker build -t isisvoice:latest -f src/app/Dockerfile .
az acr build --registry isisvoiceacr --image isisvoice:latest -f src/app/Dockerfile .

# Terraform automáticamente descargará imagen nueva
# O forzar redeploy:
az containerapp update -n isisvoice-production -g rg-isisvoice --force-deploy
```

### Escalar (si es necesario)

**Azure**:
```bash
# Editar terraform.tfvars
min_replicas = 1
max_replicas = 5

terraform apply
```

### Reducir Costos (Apagar cuando no uses)

**AWS**:
```bash
# Stop instancia EC2 (preserva datos)
aws ec2 stop-instances --instance-ids i-xxxxxxx

# Start cuando necesites
aws ec2 start-instances --instance-ids i-xxxxxxx

# Costo: $0 cuando stopped (solo storage)
```

---

## 🚨 Troubleshooting

### Whisper no responde

```bash
# SSH a instancia
ssh -i tu-key.pem ubuntu@AWS_EC2_IP

# Verificar contenedor
docker ps | grep whisper

# Si no está running:
docker start whisper

# Ver logs
docker logs whisper

# Reiniciar servicio completo
docker-compose restart whisper
```

### Ollama modelo no cargado

```bash
ssh -i tu-key.pem ubuntu@AWS_EC2_IP

# Verificar modelos
docker exec ollama ollama list

# Si falta medical3.1:
docker exec ollama ollama pull medical3.1

# Monitorear progreso
docker logs -f ollama
```

### ISISvoice en Azure no conecta a AWS

```bash
# Verificar IPs en terraform.tfvars son correctas
cat terraform/terraform.tfvars | grep -E "whisper|ollama"

# Verificar Security Group AWS permite inbound
aws ec2 describe-security-groups --group-ids sg-xxxxxxx

# Test conectividad desde tu máquina local
curl http://AWS_EC2_IP:8001/health
curl http://AWS_EC2_IP:11434/api/tags
```

### Puerto 8001 o 11434 en uso

```bash
# En la instancia AWS
ssh -i tu-key.pem ubuntu@AWS_EC2_IP

# Ver qué está usando puerto
sudo lsof -i :8001
sudo lsof -i :11434

# Matar proceso (si es necesario)
docker-compose down
```

### Docker logs vacíos

```bash
# Ver logs con timestamps
docker logs --timestamps whisper
docker logs --timestamps ollama

# Logs detallados
docker logs --follow --tail 100 whisper
```

---

## 📊 Verificación Completa

**Checklist de validación**:

```
AWS (EC2 + Docker):
  [ ] Instancia EC2 corriendo (t3.xlarge)
  [ ] Elastic IP asignada
  [ ] Security Group permite 8001, 11434, 22
  [ ] Docker instalado y running
  [ ] Contenedor Whisper corriendo en puerto 8001
  [ ] Contenedor Ollama corriendo en puerto 11434
  [ ] Modelo medical3.1 cargado en Ollama
  [ ] curl http://IP:8001/health → responde OK
  [ ] curl http://IP:11434/api/tags → responde OK

Azure (Terraform + Container Apps):
  [ ] Azure Container Registry creado
  [ ] Imagen ISISvoice pusheada a ACR
  [ ] terraform.tfvars completado
  [ ] terraform init ejecutado
  [ ] terraform apply ejecutado exitosamente
  [ ] Container App corriendo
  [ ] curl AZURE_URL/speech/health → responde OK

Testing:
  [ ] Transcripción Whisper funciona
  [ ] Inferencia Ollama funciona
  [ ] ISISvoice conecta a AWS
  [ ] Triage endpoint responde
  [ ] MongoDB conecta
  [ ] JWT tokens válidos

Monitoreo:
  [ ] Logs de Docker accesibles
  [ ] Logs de Azure Container App accesibles
  [ ] Health endpoints respondiendo
  [ ] Sin errores de timeout
```

---

## 💰 Monitoreo de Costos

```bash
# AWS
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-31 \
  --granularity MONTHLY \
  --metrics "BlendedCost"

# Azure
az costmanagement query --apply-to subscriptions \
  --require-valid-since 2024-01-01
```

---

## 📚 Referencias

- [Docker Compose Docs](https://docs.docker.com/compose/)
- [Terraform Azure Docs](https://registry.terraform.io/providers/hashicorp/azurerm/latest)
- [Whisper API](https://github.com/openai/whisper)
- [Ollama API](https://ollama.ai/library)

---

**¡Listo! ISISvoice está en producción en Azure + AWS** 🚀
