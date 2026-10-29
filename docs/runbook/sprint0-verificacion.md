# Sprint 0 · Verificación de criterios de aceptación (DoD)

Ejecutar en PowerShell desde la raíz del repo. Todo debe dar el resultado esperado
antes de pasar al Sprint 1.

| # | Criterio | Comando | Resultado esperado |
|---|---|---|---|
| 1 | Dependencias instaladas | `.\scripts\dev.ps1 setup` | `[OK] Setup terminado` |
| 2 | Lint limpio | `.\scripts\dev.ps1 lint` | `All checks passed!` y `[OK] Lint sin errores` |
| 3 | Tests unitarios | `.\scripts\dev.ps1 test` (sin Docker) | `11 passed, 3 skipped` |
| 4 | Servicios levantan | `.\scripts\dev.ps1 up` | `db`, `api`, `dashboard` en estado `Up` / `healthy` |
| 5 | API + base OK | `.\scripts\dev.ps1 check` | `status=ok database=ok` y `Dashboard responde (HTTP 200)` |
| 6 | Tests de integración | `.\scripts\dev.ps1 test` (con Docker arriba) | `14 passed` |
| 7 | Migraciones operativas | `docker compose exec api alembic current` | Sin error (todavía no hay revisiones) |
| 8 | Degradación controlada | `docker compose stop db` → `Invoke-RestMethod http://localhost:8000/api/v1/health` | Error HTTP 503; luego `docker compose start db` |
| 9 | Base no expuesta a la red | `docker compose port db 5432` | `127.0.0.1:5433` |
| 10 | Escritorio conecta | `.\scripts\dev.ps1 desktop` | Ventana con “Conectado · API y base de datos OK” |
| 11 | CI | Push a GitHub | Jobs `lint-test` y `docker-build` en verde |
