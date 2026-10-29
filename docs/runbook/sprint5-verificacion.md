# Sprint 5 · Verificación del cierre del MVP

## 1. Tests

```powershell
.\scripts\dev.ps1 setup          # suma python-multipart y truststore
.\scripts\dev.ps1 up
.\scripts\dev.ps1 lint
.\scripts\dev.ps1 test
```

Esperado con Docker arriba: **`336 passed, 1 skipped`** (CI: `308 passed, 1 skipped`). En Windows el test de backup local se saltea si
no tenés `pg_dump` instalado (el backup se prueba en el punto 4, vía Docker). En el CI corre.

## 2. Importación CSV (HU07) — 5 minutos

```powershell
.\scripts\dev.ps1 seed-demo reset
.\scripts\dev.ps1 desktop
```

1. **Importar CSV → Elegir archivo…** → `docs\manual\plantilla-demo.csv`.
2. Esperado: `3 filas · 2 válidas · 1 con errores`; la fila 4 dice
   "Cliente inexistente: 'Cliente Inexistente SA'". Nada se guardó todavía.
3. **Importar 2 facturas válidas** → confirmar → "2 facturas cargadas, 1 filas rechazadas".
4. Volvé a importar el mismo archivo: `0 válidas` ("Ya existe…"): **no duplica**.
5. Marcá *Crear los clientes que no existan* → previsualizar → `1 válidas · 1 clientes nuevos`.

También desde <http://localhost:8000/docs> → `POST /imports/invoices/preview` → *Try it out*.

## 3. Exportación (HU08)

Facturas → Estado *Vencida* → **Exportar CSV** → abrir en Excel: 6 facturas, columnas
`client_name … days_overdue`, acentos correctos.

## 4. Backup restaurable

```powershell
.\scripts\dev.ps1 backup
.\scripts\dev.ps1 backup-verify     # esperado: "RESTAURACIÓN VERIFICADA"
```

Anotá la prueba en la tabla de `docs/runbook/backup-restore.md`.

## 5. HTTPS local (antes de AWS)

Seguí `docs/runbook/despliegue-aws.md` §10 (`DOMAIN=localhost`): <https://localhost> abre el
dashboard (con aviso de certificado local) y `https://localhost/api/v1/health` responde.

## 6. Instalador 1.0.0

```powershell
.\scripts\dev.ps1 build-desktop     # dist\CashFlowManager-Setup-1.0.0.exe (con Inno Setup)
```

Con certificado de firma: `$env:CODESIGN_THUMBPRINT="..."` y
`.\scripts\build\build-desktop.ps1 -Sign`. Verificar: clic derecho en el `.exe` →
Propiedades → *Firmas digitales*.

## 7. Despliegue en AWS (HU10)

`docs/runbook/despliegue-aws.md` de punta a punta; marcar el checklist en
`docs/checklist-cierre-mvp.md`.
