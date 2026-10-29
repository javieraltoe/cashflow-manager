#!/usr/bin/env bash
# Backup diario en el servidor: dump local (14 días) + copia cifrada en S3.
# Instalar (como ubuntu):
#   chmod +x infra/aws/backup-cron.sh
#   (crontab -l 2>/dev/null; echo "15 6 * * * $HOME/cashflow-manager/infra/aws/backup-cron.sh") | crontab -
# 06:15 UTC = 03:15 en Argentina. Requiere el rol IAM de la instancia (iam-policy-backups.json).
set -euo pipefail
umask 077  # los backups contienen datos de clientes: solo los lee el dueño
cd "$(dirname "$0")/../.."

BUCKET_PREFIX="${BACKUP_S3:-s3://NOMBRE-DEL-BUCKET/cashflow}"
LOG=backups/backup.log
mkdir -p backups

{
  echo "=== $(date -u +%FT%TZ)"
  python3 scripts/backup/backup.py --compose-file docker-compose.prod.yml \
    backup --keep 14 --s3 "$BUCKET_PREFIX"
  # Domingos: restauración de prueba del último backup en una base temporal.
  if [ "$(date -u +%u)" = "7" ]; then
    latest=$(ls -1t backups/*.dump | head -n1)
    python3 scripts/backup/backup.py --compose-file docker-compose.prod.yml verify "$latest"
  fi
} >> "$LOG" 2>&1
