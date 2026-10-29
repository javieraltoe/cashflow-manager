# ADR-0001 · Decisiones de arquitectura del Sprint 0

Fecha: 2026-10-28 · Estado: aceptada

Fuente de verdad: *CashFlow Manager — Especificación MVP v1.0*.

## Decisiones

| # | Decisión | Motivo |
|---|---|---|
| 1 | **Monorepo** con `backend/`, `dashboard/`, `desktop/`, cada uno con su `requirements.txt`. | Tres despliegues distintos (imagen API, imagen dashboard, .exe) sin dependencias cruzadas. Un solo `.venv` local para simplificar VS Code. |
| 2 | **Python 3.12** en local, CI e imágenes. | Soporte estable de PySide6 y PyInstaller; misma versión en todos los entornos. |
| 3 | Dependencias **fijadas con `==`**. | Builds reproducibles; se actualizan de forma explícita. |
| 4 | **PostgreSQL 16** (`postgres:16-alpine`), sesión en **UTC**. | Spec §7/§8. Timestamps de auditoría en UTC; la zona `America/Argentina/Buenos_Aires` se aplica en la capa de negocio (`APP_TIMEZONE`) para vencimientos y agregaciones diarias. |
| 5 | Puerto de la base en el host: **127.0.0.1:5433**. | Evita conflicto con un PostgreSQL instalado en Windows y nunca se expone a la red. |
| 6 | Configuración con **pydantic-settings** leyendo `.env`; validación que impide arrancar en producción con secretos por defecto o CORS `*`. | Spec §8 y §11: secretos fuera de Git, CORS preciso. |
| 7 | API versionada en **`/api/v1`**; `GET /api/v1/health` verifica la base con `SELECT 1` y responde 200/503 sin datos sensibles. | Spec §9. |
| 8 | **Errores JSON uniformes** `{"error": {code, message, field}}` desde el inicio. | Spec §9 (contrato API). |
| 9 | **Alembic** configurado con la URL de `Settings` y convención de nombres de constraints; sin migraciones todavía. | Las tablas se crean en el Sprint 1. |
| 10 | Lint/format con **ruff** (incluye reglas de seguridad `S`); tests con **pytest**; los tests de integración se saltean sin base, salvo `REQUIRE_DB=1` (CI). | Ciclo local rápido y CI estricto. |
| 11 | El **dashboard nunca accede a la base**: solo llama a la API. | Spec §8. |
| 12 | Tareas de desarrollo en **`scripts/dev.ps1`** (no Makefile). | Entorno objetivo Windows + PowerShell. |

## Contradicciones / ambigüedades detectadas en la especificación

| Tema | Decisión mínima propuesta |
|---|---|
| §9 lista `GET /health` dentro de la API `/api/v1`. | Se expone como `/api/v1/health` (también lo usa el healthcheck Docker). |
| §8 “JWT + refresh rotatorio **o** cookies seguras para web”. | A decidir en Sprint 1/3. Propuesta: JWT de acceso corto + refresh rotatorio para escritorio **y** dashboard (el dashboard Streamlit llama a la API del lado servidor, así que no necesita cookies). |
| §2 “registros en USD optativos quedan fuera del primer corte” vs. §7 `currency CHAR(3)`. | Se mantiene la columna con default `ARS` y un CHECK `currency = 'ARS'` en el MVP. |
| §10 “rechazar clientes inexistentes (o dar opción explícita de crearlos)”. | A definir en Sprint 5; propuesta: rechazar por defecto, flag explícito `create_missing_clients`. |
| §16 asume multiusuario simultáneo y nube obligatoria. | Se asume “sí” a ambos, como indica el documento; por eso el control de concurrencia `SELECT … FOR UPDATE` del Sprint 2. |
