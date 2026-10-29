# CashFlow Manager

Aplicación de escritorio para PyMEs que centraliza clientes, cuentas por cobrar y
cobranzas, con un dashboard web privado de indicadores.

| Componente | Tecnología | Dónde corre |
|---|---|---|
| Backend API | FastAPI · SQLAlchemy 2 · Alembic · psycopg 3 | Docker (`api`) |
| Base de datos | PostgreSQL 16 | Docker (`db`) |
| Dashboard web | Streamlit · Plotly (solo consume la API) | Docker (`dashboard`) |
| Escritorio | PySide6 · httpx · PyInstaller | Windows, proceso local |

Estado: **MVP 1.0.0 — Sprint 5 cerrado** (CSV, exportación, backups, despliegue HTTPS, manual).
Decisiones en `docs/architecture/ADR-0001-sprint0.md` a `ADR-0006-sprint5.md` · estado de
cierre en `docs/checklist-cierre-mvp.md`.

---

## 1. Prerrequisitos (Windows 10/11 x64)

| Herramienta | Versión | Verificar en PowerShell |
|---|---|---|
| Python | **3.12.x** (64 bits, con *py launcher*) | `py -3.12 --version` |
| Git | 2.40+ | `git --version` |
| Docker Desktop | 4.x con backend WSL 2 | `docker version` y `docker compose version` |
| VS Code | reciente | `code --version` |

> Usamos Python 3.12 (no 3.13/3.14) porque es la versión con soporte asegurado
> para PySide6, PyInstaller y la imagen Docker `python:3.12-slim`.

Permitir scripts locales en PowerShell (una sola vez, solo para tu usuario):

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

## 2. Instalación

```powershell
cd C:\dev\cashflow-manager
git init                                  # si todavía no es un repo
.\scripts\dev.ps1 setup                   # crea .venv, instala dependencias y .env
code .                                    # abrir en VS Code e instalar extensiones recomendadas
```

Editá `.env` y cambiá al menos `POSTGRES_PASSWORD` y `SECRET_KEY`:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

> Si cambiás `POSTGRES_PASSWORD` **después** de haber levantado la base una vez,
> PostgreSQL conserva la anterior. Ejecutá `.\scripts\dev.ps1 reset-db` (borra los datos locales).

## 3. Levantar los servicios

### Opción A — todo en Docker (recomendada)

```powershell
.\scripts\dev.ps1 up       # docker compose up -d --build
.\scripts\dev.ps1 check    # verifica API + base + dashboard
```

- API y documentación: <http://localhost:8000/docs>
- Health: <http://localhost:8000/api/v1/health>
- Dashboard: <http://localhost:8501>

### Opción B — PostgreSQL en Docker, API local (para depurar en VS Code)

```powershell
.\scripts\dev.ps1 db        # solo PostgreSQL en 127.0.0.1:5433
.\scripts\dev.ps1 migrate   # alembic upgrade head
.\scripts\dev.ps1 api       # uvicorn con recarga (o F5 → "API (FastAPI local)")
```

> Si la opción A está corriendo, la API ya ocupa el puerto 8000: frená el
> contenedor con `docker compose stop api` antes de usar la opción B.

### Primer administrador

```powershell
.\scripts\dev.ps1 create-admin admin@miempresa.com.ar "Administrador"   # pide la contraseña
```

Después, en <http://localhost:8000/docs> → `POST /auth/login` → copiar `access_token`
→ botón **Authorize**.

### App de escritorio

```powershell
.\scripts\dev.ps1 desktop          # abre la app (login → Inicio, Clientes, Facturas, Pagos,
                                    # Saldo a favor, Configuración)
.\scripts\dev.ps1 build-desktop    # genera dist\CashFlowManager\CashFlowManager.exe,
                                    # el zip portable y, con Inno Setup, el instalador
```

La primera vez, en el login, el servidor es `localhost:8000`. La dirección queda guardada en
`%APPDATA%\CashFlowManager\config.json` (nunca se guardan contraseñas ni tokens).
Guía de prueba completa: `docs/runbook/sprint3-verificacion.md`.

### Dashboard web e indicadores

<http://localhost:8501> → ingresar con el mismo usuario de la app. KPIs "a hoy" (por cobrar,
vencido, % vencido, próximos 7 días, saldo a favor) y "del período" (cobrado), cobranza
mensual, vencido por antigüedad, principales deudores y próximos vencimientos, con filtros
por período y cliente y exportación CSV de cada vista.

```powershell
.\scripts\dev.ps1 seed-demo          # datos de demostración con valores documentados (HU06)
.\scripts\dev.ps1 seed-demo reset    # idem, borrando antes clientes/facturas/pagos
.\scripts\dev.ps1 seed-perf reset    # 1.000 clientes, 20.000 facturas, 50.000 pagos
.\scripts\dev.ps1 bench <email>      # mide tiempos (objetivo < 3 s)
```

Valores esperados del dataset: `docs/runbook/dataset-demo.md` · rendimiento medido:
`docs/runbook/rendimiento.md` · guía de prueba: `docs/runbook/sprint4-verificacion.md`.

## 4. Calidad

```powershell
.\scripts\dev.ps1 lint      # ruff check + ruff format --check
.\scripts\dev.ps1 format    # corrige estilo automáticamente
.\scripts\dev.ps1 test      # pytest (los de integración necesitan la base levantada)
```

Los tests de integración usan una base aparte, `cashflow_test`, que se crea y migra sola.
Cada test se revierte al terminar: tus datos de desarrollo no se tocan.

| Escenario | Resultado esperado |
|---|---|
| Sin Docker | `114 passed, 224 skipped` |
| Con `.\scripts\dev.ps1 up` o `db` | `336 passed, 1 skipped` (el skip es el backup local si no tenés `pg_dump`; en el CI corre) |

Para crear una migración nueva después de cambiar un modelo:
`.\scripts\dev.ps1 revision "descripcion"` (revisá siempre el archivo generado).

El CI (`.github/workflows/ci.yml`) corre lint, migraciones y tests contra un
PostgreSQL 16 real, y construye las imágenes Docker.

## 5. Comandos útiles

| Tarea | Comando |
|---|---|
| Ver contenedores | `.\scripts\dev.ps1 ps` |
| Logs de la API | `.\scripts\dev.ps1 logs api` |
| Detener todo | `.\scripts\dev.ps1 down` |
| Backup de la base | `.\scripts\dev.ps1 backup` |
| Probar que el backup restaura | `.\scripts\dev.ps1 backup-verify` |
| Borrar datos locales | `.\scripts\dev.ps1 reset-db` |
| Consola SQL | `docker compose exec db psql -U cashflow -d cashflow` |

## 6. API v1

| Endpoint | Quién | Descripción |
|---|---|---|
| `POST /auth/login` · `/auth/refresh` · `/auth/logout` | público | Tokens: access 15 min + refresh rotatorio 7 días |
| `GET /me` · `POST /me/password` | autenticado | Perfil y cambio de contraseña |
| `GET/POST /users` · `PATCH /users/{id}` | admin | Gestión de usuarios y roles |
| `GET/POST /clients` · `GET/PATCH /clients/{id}` | autenticado | `q`, `is_active`, `sort`, `page`, `page_size` |
| `GET/POST /invoices` · `GET/PATCH /invoices/{id}` | autenticado (anular: admin) | Filtros `client_id`, `status`, `issue_from/to`, `due_from/to`, `q`, `include_void` |
| `GET/POST /payments` · `GET /payments/{id}` | autenticado | Cobro parcial o total; el excedente queda como saldo a favor solo con `allow_credit`. Header opcional `Idempotency-Key`. Filtros `invoice_id`, `client_id`, `date_from/to`, `method`, `include_void` |
| `POST /payments/{id}/void` | admin | Anulación lógica con `reason` obligatorio |
| `GET /clients/{id}/credit` · `GET/POST /credits` · `GET /credits/{id}` | autenticado | Saldo a favor del cliente y cobros a cuenta (sin factura) |
| `POST /credits/apply` | autenticado | Imputar saldo a favor a una factura del cliente |
| `POST /credits/{id}/void` | admin | Anular un cobro a cuenta (bloqueado si ya se imputó) |
| `GET /metrics/overview` | autenticado | KPIs a hoy + cobrado del período (`date_from`, `date_to`, `client_id`) |
| `GET /metrics/collections-monthly` | autenticado | Cobrado por mes, todos los meses del período |
| `GET /metrics/aging` · `/metrics/top-debtors` · `/metrics/upcoming` | autenticado | Vencido por antigüedad, principales deudores (`limit`) y próximos vencimientos (`days`) |
| `POST /imports/invoices/preview` · `/imports/invoices/commit` | autenticado | CSV (multipart `file` + `create_missing_clients`): valida sin guardar / carga las filas válidas |
| `GET /exports/invoices.csv` | autenticado | Mismos filtros que `/invoices`, sin paginar (máx. 50.000 filas) |

Las facturas devuelven `paid_amount`, `balance`, `status` (PENDIENTE · PARCIAL · VENCIDA ·
PAGADA · ANULADA) y `days_overdue`, calculados con la fecha de hoy en Buenos Aires.
Los montos viajan como string decimal (`"125000.50"`). Cada pago devuelve además
`invoice_balance` e `invoice_status` actualizados. Registrar y anular bloquean la factura
con `SELECT … FOR UPDATE`, así dos cobros simultáneos nunca superan el importe.

## 7. Estructura

```
cashflow-manager/
  backend/            API FastAPI (app/{api,core,db,models,schemas,services}), alembic/, tests/
  dashboard/          Streamlit: app.py, components/ (api, data, charts, fmt), tests/
  desktop/            PySide6: app/core (sin Qt), app/services (cliente API), app/views,
                      app/widgets, packaging/ (PyInstaller + Inno Setup), tests/
  infra/              caddy/Caddyfile (HTTPS), aws/ (EC2, IAM, S3, cron de backups)
  docker-compose.prod.yml  .env.production.example   (producción)
  scripts/            dev.ps1, build/build-desktop.ps1, seed/, backup/
  docs/               requirements/, architecture/, api/, runbook/
  docker-compose.yml  .env.example  pyproject.toml  .github/workflows/ci.yml
```

## 8. Seguridad (desde el día 1)

- `.env` nunca se versiona; `.env.example` no contiene secretos reales.
- PostgreSQL, API y dashboard se publican solo en `127.0.0.1`.
- En `APP_ENV=production` la API no arranca con `SECRET_KEY` por defecto ni con CORS `*`,
  y `/docs` queda deshabilitado.
- Errores JSON uniformes sin detalles internos: `{"error": {"code", "message", "field"}}`.
- Montos siempre `NUMERIC(15,2)` / `Decimal`, nunca `float`.
- Contraseñas con Argon2id; refresh tokens guardados solo como hash; bloqueo tras 5 intentos.
- Rol y estado del usuario verificados contra la base en cada request.

## 9. Producción y documentación de cierre

| Documento | Para qué |
|---|---|
| `docs/runbook/despliegue-aws.md` | Servidor en AWS con HTTPS, backups en S3, costos y alertas |
| `docs/runbook/backup-restore.md` | Backups, prueba de restauración y recuperación ante incidentes |
| `docs/manual/manual-usuario.md` | Manual de uso para el cliente |
| `docs/comercial/guion-demo.md` · `propuesta-plantilla.md` | Demo de 15 minutos y propuesta comercial |
| `docs/checklist-cierre-mvp.md` | Estado de cada ítem del §18 y de las 10 historias |

## 10. Solución de problemas

| Síntoma | Causa probable / solución |
|---|---|
| `port is already allocated` en 5433/8000/8501 | Otro proceso usa el puerto: cambiá `*_HOST_PORT` en `.env`. |
| `password authentication failed` | Cambiaste la contraseña con la base ya creada → `reset-db`. |
| `dev.ps1 cannot be loaded` | Falta `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| Health devuelve 503 | La API corre pero no ve la base: `.\scripts\dev.ps1 logs db`. |
| Docker no arranca | Abrí Docker Desktop y esperá a "Engine running". |
| `429 too_many_attempts` al loguear | 5 fallos seguidos: esperá 15 min o reiniciá la API (`docker compose restart api`). |
| Tests: `permission denied to create database` | El usuario de `.env` no puede crear bases: creá `cashflow_test` a mano o definí `TEST_POSTGRES_DB`. |
