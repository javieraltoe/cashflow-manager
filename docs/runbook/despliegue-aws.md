# Despliegue en AWS con HTTPS (HU10)

Arquitectura del MVP (spec §8): **una instancia EC2** con Docker Compose (PostgreSQL, API,
dashboard y Caddy como proxy HTTPS), **backups cifrados en S3** y alertas de costo. La base
nunca se expone a Internet: solo están abiertos los puertos 80 y 443.

```
Internet ──443──> Caddy (HTTPS, Let's Encrypt) ──> /api/*  -> API FastAPI ──> PostgreSQL
                                                └─> /       -> Dashboard Streamlit
App de escritorio ──https://DOMINIO──┘                      backup diario ──> S3 (KMS)
```

## 0. Antes de empezar

| Necesitás | Ejemplo |
|---|---|
| Cuenta AWS con usuario administrador **con MFA** (no usar la cuenta root) | — |
| Un dominio o subdominio del cliente | `cobranzas.miempresa.com.ar` |
| Acceso al DNS de ese dominio | NIC.ar, Cloudflare, Route 53… |
| Región | **sa-east-1 (San Pablo)**: menor latencia desde Argentina |

## 1. Costos estimados (verificar en la calculadora antes de cotizar)

Precios on-demand de referencia, octubre 2026, sin impuestos. Se cotizan **aparte** del
desarrollo (spec §15 y §16).

| Recurso | us-east-1 | sa-east-1 |
|---|---:|---:|
| EC2 t3.small (2 vCPU, 2 GB), 730 h | USD 15,2 | USD 24,5 |
| EBS gp3 30 GB | USD 2,4 | ~USD 3,6 |
| IPv4 pública (USD 0,005/h) | USD 3,7 | USD 3,7 |
| S3 backups (pocos GB) + clave KMS | ~USD 1,5 | ~USD 1,5 |
| **Total aproximado / mes** | **~USD 23** | **~USD 33** |

Más transferencia de datos de salida (mínima para este uso). Con una Savings Plan de 1 año
la instancia baja ~30-40 %. Calculadora oficial: <https://calculator.aws/>.
RDS (base gestionada) agrega ~USD 15-30/mes; para un piloto alcanza con PostgreSQL en la
instancia **con backups diarios y prueba de restauración** (spec §8).

## 2. Presupuesto y alertas (hacerlo primero)

Billing and Cost Management → **Budgets** → Create budget → *Monthly cost budget*:
monto USD 40, alertas al 80 % real y 100 % pronosticado al email del responsable.

## 3. Crear la instancia

1. **EC2 → Launch instance**: Ubuntu Server 24.04 LTS (x86_64), tipo `t3.small`,
   key pair nuevo (guardá el `.pem`), disco **gp3 30 GB, cifrado** (Encrypted: sí).
2. **Security group** `cashflow-web`:
   | Tipo | Puerto | Origen |
   |---|---|---|
   | HTTP | 80 | 0.0.0.0/0 (Let's Encrypt y redirección a HTTPS) |
   | HTTPS | 443 | 0.0.0.0/0 |
   | SSH | 22 | **solo tu IP** (`Mi IP`) |
   Nunca abrir 5432, 8000 ni 8501.
3. **Elastic IP** → Allocate → Associate a la instancia.
4. **DNS**: registro **A** `cobranzas.miempresa.com.ar` → la Elastic IP. Esperá a que
   resuelva: `nslookup cobranzas.miempresa.com.ar`.

## 4. Preparar el servidor

```bash
ssh -i cashflow.pem ubuntu@IP-ELASTICA
git clone https://github.com/javieraltoe/cashflow-manager.git
cd cashflow-manager
bash infra/aws/bootstrap-ec2.sh       # Docker, AWS CLI, firewall, parches automáticos
exit                                  # volver a entrar para usar docker sin sudo
```

> Si el repositorio es privado, usá una *deploy key* de solo lectura en GitHub.

## 5. Configurar y levantar

```bash
ssh -i cashflow.pem ubuntu@IP-ELASTICA
cd cashflow-manager
cp .env.production.example .env && chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # para SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # para POSTGRES_PASSWORD
nano .env        # DOMAIN, ACME_EMAIL, SECRET_KEY, POSTGRES_PASSWORD
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps                  # todos "running/healthy"
docker compose -f docker-compose.prod.yml logs caddy | grep -i "certificate obtained"
```

Crear el primer administrador (credencial inicial, se cambia en el primer ingreso):

```bash
docker compose -f docker-compose.prod.yml exec api \
  python -m app.cli create-admin --email admin@miempresa.com.ar --name "Administrador"
```

## 6. Verificar HTTPS (HU10)

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://cobranzas.miempresa.com.ar/api/v1/health  # 200 (no usar -I: HEAD da 405)
curl -s  https://cobranzas.miempresa.com.ar/api/v1/health                 # {"status":"ok",...}
curl -sI http://cobranzas.miempresa.com.ar | grep -i location             # redirige a https
curl -s https://cobranzas.miempresa.com.ar/api/v1/no-existe   # {"error":{"code":"not_found",...}}
```

- Navegador: `https://cobranzas.miempresa.com.ar` → candado válido → login del dashboard.
- La documentación OpenAPI (`/docs`) está deshabilitada en producción y no se publica.
- Escritorio: en el login, Servidor `https://cobranzas.miempresa.com.ar` (sin aviso de
  "conexión sin cifrar").
- Puertos cerrados: desde tu PC, `Test-NetConnection IP -Port 5432` → `TcpTestSucceeded: False`.

## 7. Backups cifrados en S3

1. **KMS** → Create key (symmetric) → alias `cashflow-backups`.
2. **S3** → Create bucket `cashflow-backups-<cliente>` en la misma región:
   Block all public access **activado**, Versioning **activado**, Default encryption
   **SSE-KMS** con la clave anterior. Permissions → Bucket policy: pegá
   `infra/aws/s3-bucket-policy.json` reemplazando `NOMBRE-DEL-BUCKET`.
3. Management → **Lifecycle rule**: borrar versiones a los 90 días (ajustable por contrato).
4. **IAM** → Roles → Create role → *EC2* → política nueva desde
   `infra/aws/iam-policy-backups.json` (reemplazá bucket, región, cuenta e ID de clave)
   → EC2 → la instancia → Actions → Security → **Modify IAM role** → asignarlo.
   No hace falta guardar claves de acceso en el servidor.
5. En el servidor:
   ```bash
   sed -i 's#NOMBRE-DEL-BUCKET#cashflow-backups-cliente#' infra/aws/backup-cron.sh
   infra/aws/backup-cron.sh && tail backups/backup.log       # primera ejecución manual
   aws s3 ls s3://cashflow-backups-cliente/cashflow/
   (crontab -l 2>/dev/null; echo "15 6 * * * $HOME/cashflow-manager/infra/aws/backup-cron.sh") | crontab -
   ```
   Todos los días a las 03:15 (hora argentina) se genera un backup; los domingos además se
   restaura en una base temporal y se compara (ver `backup-restore.md`).

## 8. Operación

| Tarea | Comando (en el servidor, carpeta `cashflow-manager`) |
|---|---|
| Ver estado | `docker compose -f docker-compose.prod.yml ps` |
| Logs | `docker compose -f docker-compose.prod.yml logs -f --tail 100 api` |
| Actualizar versión | `git pull && docker compose -f docker-compose.prod.yml up -d --build` (aplica migraciones) |
| Backup manual | `python3 scripts/backup/backup.py --compose-file docker-compose.prod.yml backup` |
| Reiniciar | `docker compose -f docker-compose.prod.yml restart api dashboard` |

Antes de actualizar: hacé un backup manual. Las migraciones se aplican solas al arrancar la API.

## 9. Rotación de credenciales (spec §15 "credenciales iniciales rotables")

| Credencial | Cómo rotarla | Efecto |
|---|---|---|
| Contraseña de un usuario | Escritorio → Configuración, o el admin la restablece | Cierra las sesiones de ese usuario |
| `SECRET_KEY` | Nuevo valor en `.env` → `up -d api` | Todos vuelven a ingresar |
| `POSTGRES_PASSWORD` | `docker compose exec db psql -U cashflow -c "ALTER USER cashflow PASSWORD '...'"`, actualizar `.env`, `up -d api` | Sin corte de datos |
| Llave SSH | Nuevo key pair, reemplazar en `~/.ssh/authorized_keys` | — |

## 10. Probar HTTPS en tu PC antes de ir a AWS (opcional)

```powershell
Copy-Item .env.production.example .env.prod-local   # ignorado por Git
# editar: DOMAIN=localhost, ACME_EMAIL=tu@email, secretos de prueba
docker compose -p cashflow-https -f docker-compose.prod.yml --env-file .env.prod-local up -d --build
docker compose -p cashflow-https -f docker-compose.prod.yml --env-file .env.prod-local exec api python -m app.cli create-admin --email tu@email --name "Prueba HTTPS"
```

`-p cashflow-https` es imprescindible: sin él, este stack usa el mismo nombre de proyecto
que el de desarrollo, reemplaza sus contenedores y monta su base (`cashflow_pgdata`). Con
él, la prueba tiene base propia (vacía: por eso se crea un administrador) y el entorno de
desarrollo sigue funcionando en paralelo.

Abrí <https://localhost>: Caddy usa una autoridad local, así que el navegador va a advertir
que el certificado no es de confianza (es esperable; con un dominio real el certificado es
de Let's Encrypt). Al terminar:
`docker compose -p cashflow-https -f docker-compose.prod.yml --env-file .env.prod-local down -v`
(`-v` borra la base de prueba; la de desarrollo no se toca).
