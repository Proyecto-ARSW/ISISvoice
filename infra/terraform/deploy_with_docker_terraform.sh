#!/usr/bin/env bash
set -euo pipefail

TF_VERSION="1.9.8"
IMAGE="hashicorp/terraform:${TF_VERSION}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker no esta instalado."
  exit 1
fi

if [[ ! -f "${SCRIPT_DIR}/terraform.tfvars" ]]; then
  echo "Error: falta ${SCRIPT_DIR}/terraform.tfvars"
  echo "Copia terraform.tfvars.example o usa el archivo generado y completa key_name."
  exit 1
fi

# Detectar credenciales AWS disponibles
HAS_AWS_ENV=false
if [[ -n "${AWS_ACCESS_KEY_ID:-}" && -n "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
  HAS_AWS_ENV=true
fi

HAS_AWS_FILES=false
if [[ -f "${HOME}/.aws/credentials" || -f "${HOME}/.aws/config" ]]; then
  HAS_AWS_FILES=true
fi

if [[ "${HAS_AWS_ENV}" == false && "${HAS_AWS_FILES}" == false ]]; then
  echo "Error: no hay credenciales AWS en variables de entorno ni en ~/.aws"
  echo "Configura AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY (y opcional AWS_SESSION_TOKEN),"
  echo "o ejecuta aws configure antes de correr este script."
  exit 1
fi

AWS_MOUNT_ARGS=()
if [[ "${HAS_AWS_FILES}" == true ]]; then
  AWS_MOUNT_ARGS+=("-v" "${HOME}/.aws:/root/.aws:ro")
fi

echo "[1/3] terraform init"
docker run --rm \
  -v "${SCRIPT_DIR}:/workspace" \
  "${AWS_MOUNT_ARGS[@]}" \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  -e AWS_SESSION_TOKEN \
  -e AWS_DEFAULT_REGION \
  -w /workspace \
  "${IMAGE}" init

echo "[2/3] terraform plan"
docker run --rm \
  -v "${SCRIPT_DIR}:/workspace" \
  "${AWS_MOUNT_ARGS[@]}" \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  -e AWS_SESSION_TOKEN \
  -e AWS_DEFAULT_REGION \
  -w /workspace \
  "${IMAGE}" plan -out=tfplan

echo "[3/3] terraform apply"
docker run --rm \
  -v "${SCRIPT_DIR}:/workspace" \
  "${AWS_MOUNT_ARGS[@]}" \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  -e AWS_SESSION_TOKEN \
  -e AWS_DEFAULT_REGION \
  -w /workspace \
  "${IMAGE}" apply -auto-approve tfplan

echo "Instancia creada. Outputs:"
docker run --rm \
  -v "${SCRIPT_DIR}:/workspace" \
  "${AWS_MOUNT_ARGS[@]}" \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  -e AWS_SESSION_TOKEN \
  -e AWS_DEFAULT_REGION \
  -w /workspace \
  "${IMAGE}" output
