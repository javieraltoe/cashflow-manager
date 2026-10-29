#!/usr/bin/env bash
# Prepara una instancia EC2 Ubuntu 24.04 para CashFlow Manager.
# Uso (como ubuntu, una sola vez):  bash infra/aws/bootstrap-ec2.sh
# Instala Docker Engine + Compose (repositorio oficial), AWS CLI, firewall y
# actualizaciones automáticas de seguridad.
set -euo pipefail

echo "==> Actualizando el sistema"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
sudo apt-get install -y ca-certificates curl gnupg ufw unattended-upgrades python3 unzip

echo "==> Docker Engine y Compose (repositorio oficial de Docker)"
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"

echo "==> AWS CLI v2 (para copiar backups a S3)"
if ! command -v aws >/dev/null; then
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o /tmp/awscliv2.zip
  unzip -q /tmp/awscliv2.zip -d /tmp && sudo /tmp/aws/install && rm -rf /tmp/aws /tmp/awscliv2.zip
fi

echo "==> Firewall: solo SSH, HTTP y HTTPS"
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw --force enable

echo "==> Actualizaciones automáticas de seguridad"
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

echo
echo "Listo. Cerrá la sesión SSH y volvé a entrar (para usar docker sin sudo)."
echo "Siguiente paso: docs/runbook/despliegue-aws.md, sección 4."
