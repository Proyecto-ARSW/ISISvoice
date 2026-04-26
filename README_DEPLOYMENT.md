# ISISvoice - Deployment Guide

**Arquitectura Separada**: ISISvoice (FastAPI) en Azure + Whisper/Ollama en AWS

## 📋 Índice

1. [Descripción General](#descripción-general)
2. [Cambios Realizados](#cambios-realizados)
3. [Requisitos Previos](#requisitos-previos)
4. [Paso a Paso: AWS (Whisper & Ollama)](#paso-a-paso-aws-whisper--ollama)
5. [Paso a Paso: Azure (ISISvoice)](#paso-a-paso-azure-isisvoice)
6. [Verificación y Pruebas](#verificación-y-pruebas)
7. [Solución de Problemas](#solución-de-problemas)
8. [Optimización de Costos](#optimización-de-costos)

---

## 📐 Descripción General

ISISvoice ahora está **separado en dos partes**:

```
┌────────────────────────────────────────────────────────────────┐
│                        Azure (Your Account)                    │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Container Apps (Scale-to-Zero)                          │  │
│  │  • ISISvoice API (FastAPI)                               │  │
│  │  • Health: /speech/health                                │  │
│  │  • Triage: POST /triage/process                          │  │
│  │  • Clinical: POST /clinical/session                      │  │
│  └──────────────────────────────────────────────────────────┘  │
│         │                            │                          │
│         └──────────────┬─────────────┘                          │
│                        │                                        │
│                   MongoDB Atlas                                 │
│                   (Your Account)                                │
└────────────────────────────────────────────────────────────────┘
         │                                    │
         │                                    │
    ┌────▼──────────────────────┐     ┌──────▼────────────────────┐
    │      AWS (Your Account)   │     │     AWS (Your Account)    │
    │  ┌────────────────────┐   │     │  ┌────────────────────┐   │
    │  │  Whisper Server    │   │     │  │  Ollama Server     │   │
    │  │  FastAPI           │   │     │  │  (Medical Model)   │   │
    │  │  Port: 8001        │   │     │  │  Port: 11434       │   │
    │  │  EC2: t3.medium    │   │     │  │  EC2: t3.xlarge    │   │
    │  └────────────────────┘   │     │  └────────────────────┘   │
    │                           │     │                           │
    │  Elastic IP (Static)      │     │  Elastic IP (Static)      │
    └───────────────────────────┘     └───────────────────────────┘
```

### Ventajas

✅ **ISISvoice optimizado**: Solo código de API, sin modelos locales  
✅ **Azure Student Tier**: Costo bajo con escala a cero  
✅ **Flexibilidad**: Cambia URLs de Whisper/Ollama sin redeploy  
✅ **Escalabilidad**: Cada servicio puede escalar independientemente  
✅ **Mantenibilidad**: Separación clara de responsabilidades  

---

## 🔄 Cambios Realizados

### Código ISISvoice

**1. `.env`** - Actualizado con variables para AWS
```env
# Whisper - AWS
WHISPER_API_URL=http://YOUR_WHISPER_AWS_IP:8001
WHISPER_MODEL=large-v3
WHISPER_LANGUAGE=es
WHISPER_TIMEOUT_SECONDS=45

# Ollama - AWS
OLLAMA_BASE_URL=http://YOUR_OLLAMA_AWS_IP:11434
OLLAMA_MODEL=medical3.1
OLLAMA_TIMEOUT_SECONDS=12

# MongoDB Atlas (sin cambios)
MONGODB_URI=mongodb+srv://...
```

**2. `src/app/core/settings.py`** - Agregada variable WHISPER_API_URL
```python
self.whisper_api_url = os.getenv("WHISPER_API_URL", "http://localhost:8001")
self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
```

**3. `src/app/services/speech_service.py`** - Completamente reescrito
- ❌ Eliminado: Carga local de modelo Whisper
- ✅ Agregado: Cliente HTTP async (httpx) para llamar Whisper en AWS
- Método nuevo: `_transcribe_remote()` que hace POST a `WHISPER_API_URL`

**4. `src/app/requirements.txt`** - Limpiado
- ❌ Eliminado: `openai-whisper`, `torch`, `torchaudio`, `librosa`, `soundfile`, `miniaudio`
- ✅ Mantenido: `httpx` (para llamadas a APIs remotas)

### Resultado

- **Tamaño imagen Docker**: ~500MB (antes: ~4GB con Whisper+Torch)
- **Tiempo arranque**: <1min (antes: 2-3min cargando modelos)
- **Memoria RAM**: ~200MB (antes: ~2GB)
- **Escalabilidad**: Puede escalar a 0 replicas con Container Apps

---

## 📋 Requisitos Previos

### General

- [ ] **Git** instalado
- [ ] **Docker** instalado (para construir imagen)
- [ ] **Terraform** >= 1.0 (para desplegar en Azure)

### AWS

- [ ] **Cuenta AWS** activa
- [ ] **Par de claves EC2** creado (para SSH)
- [ ] **Budget**: ~$100-150/mes para t3.medium (Whisper) + t3.xlarge (Ollama)

### Azure

- [ ] **Cuenta Azure** con beneficios de estudiante ($50 USD/mes)
- [ ] **Acceso a subscripción Azure** diferente a tu cuenta personal
- [ ] **Azure CLI** instalado (opcional pero recomendado)

### Datos Existentes

- [ ] **MongoDB Atlas** URI (ya tienes esta)
- [ ] **JWT Secret** (tienes este)

---

## 🚀 Paso a Paso: AWS (Whisper & Ollama)

### 1. Desplegar Whisper (Servidor de Transcripción)

#### 1.1 Crear EC2 Instance

```bash
# Opción A: AWS Console
# 1. Ir a EC2 Dashboard → Instances → Launch Instance
# 2. AMI: Ubuntu 22.04 LTS
# 3. Instance type: t3.medium (2 vCPU, 4GB RAM)
# 4. Storage: 30GB gp3
# 5. Security Group: Crear nuevo, permitir puerto 8001
# 6. Review y Launch

# Opción B: AWS CLI
aws ec2 run-instances \
  --image-ids ami-0c55b159cbfafe1f0 \
  --instance-type t3.medium \
  --key-name tu-key-pair \
  --security-groups whisper-sg \
  --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3}"
```

#### 1.2 Asignar Elastic IP (Static IP)

```bash
# Desde AWS Console o CLI:
# 1. EC2 Dashboard → Network & Security → Elastic IPs
# 2. Allocate Elastic IP
# 3. Asociar con tu instancia Whisper
# 4. Anotar la IP: WHISPER_IP = _____________________
```

#### 1.3 Conectar vía SSH y Instalar

```bash
# SSH a la instancia
ssh -i tu-key.pem ubuntu@WHISPER_IP

# Descargar y ejecutar script de instalación
cd /tmp
wget https://raw.githubusercontent.com/tu-repo/ISISvoice/main/aws-servers/install-whisper.sh
chmod +x install-whisper.sh
./install-whisper.sh

# Esperar a que se cargue el modelo (5-10 minutos)
journalctl -u whisper -f
```

#### 1.4 Verificar Whisper

```bash
# Desde tu máquina local
curl http://WHISPER_IP:8001/health

# Debes ver:
# {"status":"healthy","service":"whisper-api","model":"large-v3","version":"1.0"}
```

**✓ Anotado**: `WHISPER_IP = __________________`

---

### 2. Desplegar Ollama (Servidor de LLM)

#### 2.1 Crear otra EC2 Instance

```bash
# Similar a Whisper pero:
# - Instance type: t3.xlarge (4 vCPU, 16GB RAM) o mayor
# - Storage: 50GB gp3 (para modelos médicos)
```

#### 2.2 Asignar Elastic IP

```bash
# Similar a Whisper
# Anotar la IP: OLLAMA_IP = _____________________
```

#### 2.3 Conectar e Instalar

```bash
ssh -i tu-key.pem ubuntu@OLLAMA_IP

cd /tmp
wget https://raw.githubusercontent.com/tu-repo/ISISvoice/main/aws-servers/install-ollama.sh
chmod +x install-ollama.sh
./install-ollama.sh

# Ollama se instala automáticamente
# Ahora necesitas bajar el modelo (toma tiempo)
```

#### 2.4 Descargar Modelo Médico

```bash
# En tmux (para que continue si se desconecta)
tmux new-session -d -s ollama "ollama pull medical3.1"

# O en background
nohup ollama pull medical3.1 > /var/log/ollama-pull.log 2>&1 &

# Monitorear progreso
tail -f /var/log/ollama-pull.log
# Esperar hasta que diga "successfully pulled"
```

#### 2.5 Verificar Ollama

```bash
# Desde tu máquina local
curl http://OLLAMA_IP:11434/api/tags

# Debes ver algo como:
# {"models":[{"name":"medical3.1:latest",...}]}
```

**✓ Anotado**: `OLLAMA_IP = __________________`

---

### 3. Configurar Seguridad en AWS

```bash
# Restricciones de acceso para Whisper
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxx \
  --protocol tcp \
  --port 8001 \
  --cidr TU_IP/32  # Tu IP actual de oficina

# Lo mismo para Ollama
aws ec2 authorize-security-group-ingress \
  --group-id sg-yyyyy \
  --protocol tcp \
  --port 11434 \
  --cidr TU_IP/32
```

---

## 🏗️ Paso a Paso: Azure (ISISvoice)

### 1. Preparar Imagen Docker

```bash
# Desde tu máquina, en la carpeta del proyecto
cd /path/to/ISISvoice

# Construir imagen
docker build -t isisvoice:latest -f src/app/Dockerfile .

# Verificar que se construyó
docker images | grep isisvoice
```

### 2. Crear Azure Container Registry (ACR)

```bash
# Login a Azure
az login
az account set --subscription "TU_SUBSCRIPTION_ID"

# Crear ACR (nombre único en todo Azure)
az acr create \
  --resource-group rg-isisvoice-prod \
  --name isisvoiceacr \
  --sku Basic

# O usar uno existente si ya tienes
# Obtener login server
az acr show --name isisvoiceacr --query loginServer -o tsv
# Salida: isisvoiceacr.azurecr.io
```

### 3. Push Imagen a ACR

```bash
# Opción A: Usar az acr build (recomendado)
az acr build \
  --registry isisvoiceacr \
  --image isisvoice:latest \
  --file src/app/Dockerfile .

# Opción B: Push manual
docker tag isisvoice:latest isisvoiceacr.azurecr.io/isisvoice:latest
az acr login --name isisvoiceacr
docker push isisvoiceacr.azurecr.io/isisvoice:latest
```

### 4. Configurar Terraform

```bash
cd terraform/

# Copiar archivo de ejemplo
cp terraform.tfvars.example terraform.tfvars

# Editar y llenar valores
nano terraform.tfvars
```

**Valores a configurar en `terraform.tfvars`**:

```hcl
# Azure
location              = "eastus"
container_registry_name = "isisvoiceacr"  # DEBE SER ÚNICO

# Imagen Docker
isisvoice_image = "isisvoiceacr.azurecr.io/isisvoice:latest"

# AWS Endpoints (las IPs que anotaste)
whisper_api_url = "http://WHISPER_IP:8001"
ollama_base_url = "http://OLLAMA_IP:11434"

# MongoDB (tu URI existente)
mongodb_uri = "mongodb+srv://christianromerom_db_user:JwLpY7RmKn2XZhOm@siti.oz3u7fx.mongodb.net/?appName=SITI"
mongodb_db  = "voice_medical"

# JWT Secret (tu secret existente)
jwt_secret = "ASCLEPIO_ARSW-SECRET-2026-PROYECTO-HOSPITALARIO-CORE"
```

### 5. Desplegar con Terraform

```bash
# Inicializar Terraform
terraform init

# Validar configuración
terraform validate

# Ver qué se va a crear
terraform plan

# Desplegar
terraform apply

# Esperar a que complete... (2-3 minutos)
```

**✓ Anotar salida**:
```
Outputs:
isisvoice_url = "https://isisvoice-production.azuremanageddata.com"
```

---

## ✅ Verificación y Pruebas

### 1. Test de Conectividad

```bash
# Test Whisper
curl http://WHISPER_IP:8001/health
# {"status":"healthy",...}

# Test Ollama
curl http://OLLAMA_IP:11434/api/tags
# {"models":[...]}

# Test ISISvoice
curl https://ISISVOICE_URL/speech/health
# {status: "healthy",...}
```

### 2. Test de Transcripción Completo

```bash
# Crear archivo de audio (o usar uno existente)
# Guardar como: test-audio.wav

# Convertir a base64
base64 test-audio.wav > audio_b64.txt

# Llamar endpoint de Whisper directamente
curl -X POST http://WHISPER_IP:8001/transcribe \
  -H "Content-Type: application/json" \
  -d '{
    "audio_base64": "'$(cat audio_b64.txt)'",
    "language": "es",
    "file_name": "test.wav"
  }'

# Debes ver la transcripción del audio
```

### 3. Test de API de Triage

```bash
# Obtener token JWT (necesitarás uno válido)
# Si no tienes, crea uno para testing

curl -X POST https://ISISVOICE_URL/triage/process \
  -H "Authorization: Bearer TU_JWT_TOKEN" \
  -F "audio=@test-audio.wav" \
  -F "patient_id=test-patient"

# Debes ver respuesta con triage result
```

---

## 🔧 Solución de Problemas

### Whisper no responde

```bash
# SSH a instancia
ssh -i tu-key.pem ubuntu@WHISPER_IP

# Verificar si servicio está corriendo
sudo systemctl status whisper

# Ver logs
journalctl -u whisper -n 50

# Reiniciar servicio
sudo systemctl restart whisper

# Verificar puerto está escuchando
sudo netstat -tlnp | grep 8001
```

### Ollama no responde

```bash
ssh -i tu-key.pem ubuntu@OLLAMA_IP

# Verificar servicio
sudo systemctl status ollama

# Logs
sudo journalctl -u ollama -n 50

# Modelo no cargado aún?
ollama list
# Si está vacío, el pull aún está en progreso
```

### ISISvoice en Azure no conecta a AWS

1. Verificar Security Groups en AWS permiten inbound desde tu IP
2. Verificar IPs en `terraform.tfvars` son correctas
3. Revisar logs de Container App:

```bash
az containerapp logs show \
  --name isisvoice-production \
  --resource-group rg-isisvoice-prod \
  --follow
```

### MongoDB connection timeout

1. Verificar tu IP está whitelisted en MongoDB Atlas Network Access
2. Verificar connection string está correcta en `.env`
3. Probar conectividad:

```bash
# Desde tu máquina
mongosh "mongodb+srv://user:pass@cluster.mongodb.net/database"
```

---

## 💰 Optimización de Costos

### Azure

Con `min_replicas = 0` (scale to zero):
- **Idle**: $0.05/día
- **1-2 vCPU, 2-4GB RAM**: $0.05-0.20/hora

### AWS

- **Whisper (t3.medium)**: $25-30/mes (24/7)
  - Opción: Stop cuando no se use: $5-10/mes

- **Ollama (t3.xlarge)**: $130-150/mes (24/7)
  - Opción: Stop cuando no se use: $30-50/mes

**Total estimado con scale-down**:
- Azure: $1-2/mes
- AWS: $35-60/mes
- **TOTAL: $36-62/mes** ✅ Dentro del presupuesto de estudiante

### Configurar Auto-Shutdown en AWS

```bash
# Opción 1: Manual (cuando no necesites)
aws ec2 stop-instances --instance-ids i-whisper i-ollama

# Opción 2: Lambda + EventBridge (automático)
# Requiere configuración más avanzada
# Ver: AWS Lambda scheduling docs
```

---

## 📚 Archivos Importantes

```
ISISvoice/
├── .env                          # Variables de ambiente (COMPLETAR IPs)
├── src/app/
│   ├── core/settings.py          # ✓ Modificado - añadida WHISPER_API_URL
│   ├── services/speech_service.py # ✓ Reescrito - cliente HTTP remoto
│   └── requirements.txt           # ✓ Limpiado - eliminadas dependencias pesadas
│
├── terraform/                    # Nueva carpeta - Despliegue Azure
│   ├── main.tf                   # Configuración principal
│   ├── variables.tf              # Variables
│   ├── terraform.tfvars.example  # Ejemplo de valores
│   └── README.md                 # Guía detallada
│
├── aws-servers/                  # Nueva carpeta - Servidores AWS
│   ├── whisper_server.py         # Servidor FastAPI para Whisper
│   ├── install-whisper.sh        # Script de instalación
│   ├── install-ollama.sh         # Script de instalación Ollama
│   └── README.md                 # Guía rápida
│
├── AWS_DEPLOYMENT_GUIDE.md       # Guía detallada AWS
├── DEPLOYMENT_GUIDE.sh           # Script interactivo de despliegue
└── README_DEPLOYMENT.md          # ESTE ARCHIVO
```

---

## 📞 Resumen Checklist

### Antes de Empezar

- [ ] Tienes AWS account
- [ ] Tienes Azure account con beneficios estudiante
- [ ] Tienes Docker instalado
- [ ] Tienes Terraform instalado

### AWS Deployment

- [ ] Whisper EC2 instance creada y corriendo
- [ ] Whisper Elastic IP asignada
- [ ] Whisper responde en `http://WHISPER_IP:8001/health`
- [ ] Ollama EC2 instance creada y corriendo
- [ ] Ollama Elastic IP asignada
- [ ] Ollama modelo `medical3.1` completamente cargado
- [ ] Security Groups configurados

### Azure Deployment

- [ ] Imagen Docker construida localmente
- [ ] Imagen pushed a Azure Container Registry
- [ ] `terraform/terraform.tfvars` completado con valores
- [ ] `terraform init` ejecutado
- [ ] `terraform apply` ejecutado exitosamente
- [ ] `terraform output` muestra URLs

### Testing

- [ ] Whisper responde en `/health`
- [ ] Ollama responde en `/api/tags`
- [ ] ISISvoice responde en `/speech/health`
- [ ] Test de transcripción completo funciona

---

## 🎯 Próximos Pasos Opcionales

1. **Configurar CI/CD**: GitHub Actions para auto-deploy
2. **Monitorear costos**: AWS Cost Explorer, Azure Cost Management
3. **Configurar alertas**: CloudWatch para AWS, Application Insights para Azure
4. **Webhook integration**: Conectar eventos de triage a sistemas externos
5. **Escalar según demanda**: Ajustar replicas en Azure según uso

---

## 📖 Documentación Adicional

- Más detalles AWS: Ver `AWS_DEPLOYMENT_GUIDE.md`
- Más detalles Azure/Terraform: Ver `terraform/README.md`
- Servidor Whisper: Ver `aws-servers/whisper_server.py`
- Script interactivo: Ejecutar `bash DEPLOYMENT_GUIDE.sh`

---

**¡Listo para desplegar ISISvoice! 🚀**

Si tienes preguntas, revisa los archivos README específicos o contáctame.
