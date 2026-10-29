# Backup y restauración (spec §8, §11 y checklist §18)

Herramienta única: `scripts/backup/backup.py` (Python estándar, sin dependencias).

| Acción | Desarrollo (Windows) | Servidor |
|---|---|---|
| Backup | `.\scripts\dev.ps1 backup` | automático diario (`infra/aws/backup-cron.sh`) |
| Probar que restaura | `.\scripts\dev.ps1 backup-verify` | automático los domingos |
| Restaurar | ver abajo | ver abajo |

Cada backup es un `pg_dump` en formato *custom* (`.dump`) con su `.sha256`. Se guardan en
`backups/` (fuera de Git) y, en el servidor, se copian a S3 cifrados con KMS.

## Prueba de restauración (obligatoria antes de cargar datos reales)

```powershell
.\scripts\dev.ps1 seed-demo reset      # datos conocidos
.\scripts\dev.ps1 backup
.\scripts\dev.ps1 backup-verify        # restaura en "cashflow_restore_check" y compara
```

Resultado esperado (con el dataset demo):

```
Dato                                Base actual    Backup restaurado
users                                         1                    1
clients                                       7                    7
invoices                                     17                   17
payments                                     11                   11
client_credits                                2                    2
...
suma_facturas                        2355000.00           2355000.00
suma_pagos_vigentes                  1405000.00           1405000.00
version_esquema                            0003                 0003

RESTAURACIÓN VERIFICADA: el backup está completo.
```

Si hay diferencias porque hubo movimientos después del backup, el script las marca y
termina con código 1 (es lo esperado en ese caso). Un archivo alterado o incompleto se
rechaza antes de restaurar por no coincidir con su `.sha256`.

Registro de pruebas (completar en cada prueba):

| Fecha | Entorno | Backup | Resultado | Responsable |
|---|---|---|---|---|
| 2026-10-29 | Desarrollo (Docker, Windows) | `cashflow_cashflow_20261029_162523Z.dump` (27 KB) | RESTAURACIÓN VERIFICADA: 11 datos iguales (conteos, totales y esquema 0003) | Claude Code |

## Restaurar ante un incidente

1. Detener la aplicación (evita escrituras durante la restauración):
   ```bash
   docker compose -f docker-compose.prod.yml stop api dashboard
   ```
2. Si el backup está solo en S3, descargarlo:
   ```bash
   aws s3 cp s3://cashflow-backups-cliente/cashflow/ARCHIVO.dump backups/
   aws s3 cp s3://cashflow-backups-cliente/cashflow/ARCHIVO.dump.sha256 backups/
   ```
3. Restaurar **primero en una base aparte** para revisar:
   ```bash
   python3 scripts/backup/backup.py --compose-file docker-compose.prod.yml \
     restore backups/ARCHIVO.dump --target-db cashflow_revision
   ```
4. Reemplazar la base principal (pide escribir RESTAURAR):
   ```bash
   python3 scripts/backup/backup.py --compose-file docker-compose.prod.yml \
     restore backups/ARCHIVO.dump --replace
   docker compose -f docker-compose.prod.yml up -d api dashboard
   ```
5. Verificar con el dashboard y `GET /api/v1/health`. Avisar a los usuarios qué datos
   posteriores al backup hay que volver a cargar.

En Windows (desarrollo) los mismos comandos son `.\.venv\Scripts\python.exe
scripts\backup\backup.py restore ...` (por defecto usa el contenedor `db` de Docker).

## Objetivos

| Indicador | Valor del MVP |
|---|---|
| RPO (datos que se pueden perder) | hasta 24 h (backup diario) |
| RTO (tiempo de recuperación) | ~30 min con el procedimiento de arriba |
| Retención | 14 días en el servidor · 90 días en S3 (configurable) |
