# CashFlow Manager

Aplicación de escritorio para PyMEs que centraliza clientes, cuentas por cobrar y
cobranzas, con un dashboard web privado de indicadores.

| Componente | Tecnología | Dónde corre |
|---|---|---|
| Backend API | FastAPI · SQLAlchemy 2 · Alembic · psycopg 3 | Docker (`api`) |
| Base de datos | PostgreSQL 16 | Docker (`db`) |
| Dashboard web | Streamlit · Plotly (solo consume la API) | Docker (`dashboard`) |
| Escritorio | PySide6 · httpx · PyInstaller | Windows, proceso local |

Estado: **Sprint 2 — pagos y saldo a favor** (sobre auth, clientes y facturas del Sprint 1). Decisiones en
`docs/architecture/ADR-0001-sprint0.md`, `ADR-0002-sprint1.md` y `ADR-0003-sprint2.md`.

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
.\scripts\dev.ps1 desktop   # ventana que prueba la conexión con la API
```

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
| Sin Docker | `47 passed, 118 skipped` |
| Con `.\scripts\dev.ps1 up` o `db` | `165 passed` |

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
| Borrar datos locales | `.\scripts\dev.ps1 reset-db` |
| Consola SQL | `docker compose exec db psql -U cashflow -d cashflow` |

## 6. API v1 (Sprint 2)

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

Las facturas devuelven `paid_amount`, `balance`, `status` (PENDIENTE · PARCIAL · VENCIDA ·
PAGADA · ANULADA) y `days_overdue`, calculados con la fecha de hoy en Buenos Aires.
Los montos viajan como string decimal (`"125000.50"`). Cada pago devuelve además
`invoice_balance` e `invoice_status` actualizados. Registrar y anular bloquean la factura
con `SELECT … FOR UPDATE`, así dos cobros simultáneos nunca superan el importe.

## 7. Estructura

```
cashflow-manager/
  backend/            API FastAPI (app/{api,core,db,models,schemas,services}), alembic/, tests/
  dashboard/          Streamlit (app.py, pages/, components/)
  desktop/            PySide6 (app/{views,widgets,services})
  infra/              docker/, nginx/, aws/        (despliegue: Sprint 5)
  scripts/            dev.ps1, seed/, backup/, build/
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

## 9. Solución de problemas

| Síntoma | Causa probable / solución |
|---|---|
| `port is already allocated` en 5433/8000/8501 | Otro proceso usa el puerto: cambiá `*_HOST_PORT` en `.env`. |
| `password authentication failed` | Cambiaste la contraseña con la base ya creada → `reset-db`. |
| `dev.ps1 cannot be loaded` | Falta `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| Health devuelve 503 | La API corre pero no ve la base: `.\scripts\dev.ps1 logs db`. |
| Docker no arranca | Abrí Docker Desktop y esperá a "Engine running". |
| `429 too_many_attempts` al loguear | 5 fallos seguidos: esperá 15 min o reiniciá la API (`docker compose restart api`). |
| Tests: `permission denied to create database` | El usuario de `.env` no puede crear bases: creá `cashflow_test` a mano o definí `TEST_POSTGRES_DB`. |
