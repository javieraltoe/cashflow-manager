# CashFlow Manager

Aplicación de escritorio para PyMEs que centraliza clientes, cuentas por cobrar y
cobranzas, con un dashboard web privado de indicadores.

| Componente | Tecnología | Dónde corre |
|---|---|---|
| Backend API | FastAPI · SQLAlchemy 2 · Alembic · psycopg 3 | Docker (`api`) |
| Base de datos | PostgreSQL 16 | Docker (`db`) |
| Dashboard web | Streamlit · Plotly (solo consume la API) | Docker (`dashboard`) |
| Escritorio | PySide6 · httpx · PyInstaller | Windows, proceso local |

Estado: **Sprint 0 — setup**. Ver `docs/architecture/ADR-0001-sprint0.md`.

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

## 6. Estructura

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

## 7. Seguridad (desde el día 1)

- `.env` nunca se versiona; `.env.example` no contiene secretos reales.
- PostgreSQL, API y dashboard se publican solo en `127.0.0.1`.
- En `APP_ENV=production` la API no arranca con `SECRET_KEY` por defecto ni con CORS `*`,
  y `/docs` queda deshabilitado.
- Errores JSON uniformes sin detalles internos: `{"error": {"code", "message", "field"}}`.
- Montos siempre `NUMERIC(15,2)` / `Decimal`, nunca `float`.

## 8. Solución de problemas

| Síntoma | Causa probable / solución |
|---|---|
| `port is already allocated` en 5433/8000/8501 | Otro proceso usa el puerto: cambiá `*_HOST_PORT` en `.env`. |
| `password authentication failed` | Cambiaste la contraseña con la base ya creada → `reset-db`. |
| `dev.ps1 cannot be loaded` | Falta `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| Health devuelve 503 | La API corre pero no ve la base: `.\scripts\dev.ps1 logs db`. |
| Docker no arranca | Abrí Docker Desktop y esperá a "Engine running". |
