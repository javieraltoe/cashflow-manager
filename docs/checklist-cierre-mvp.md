# Checklist de cierre del MVP (spec §18)

Estado al 2026-10-29. ✅ verificado con pruebas automáticas · 🟡 listo, falta ejecutarlo
en el entorno real · ⬜ pendiente.

| Ítem §18 | Estado | Evidencia |
|---|---|---|
| Login y roles verificados | ✅ | `test_auth_api.py`, `test_users_api.py`, `test_permissions.py` (todas las rutas) |
| Clientes, facturas y pagos probados | ✅ | `test_clients_api.py`, `test_invoices_api.py`, `test_payments_*.py`, `test_credits_api.py`, interfaz del escritorio |
| Cálculos y estados conciliados con datos semilla | ✅ | HU06: `test_metrics_hu06.py` + `docs/runbook/dataset-demo.md` |
| Dashboard autenticado y KPIs correctos | ✅ | `dashboard/tests/` (incluye la app Streamlit completa) |
| Importación/Exportación CSV operativas | ✅ | HU07 `test_imports_api.py`, HU08 `test_exports_api.py`, escritorio |
| Pruebas automáticas y migraciones exitosas | ✅ | CI: lint, `alembic upgrade/check/downgrade/upgrade`, tests |
| Instalador Windows probado en otra PC | 🟡 | `build-desktop.ps1` + Inno Setup; probar en una PC sin Python (`sprint3-verificacion.md` §3) |
| Deploy HTTPS y backup restaurable | 🟡 / ✅ | Backup y verificación por restauración probados (`test_backup_script.py`); despliegue según `despliegue-aws.md` |
| Manual, demo y presupuesto de soporte | ✅ | `docs/manual/manual-usuario.md`, `docs/comercial/guion-demo.md`, `docs/comercial/propuesta-plantilla.md` |

## Historias de usuario

| HU | Prioridad | Estado |
|---|---|---|
| HU01 · Login y roles | P0 | ✅ |
| HU02 · Clientes | P0 | ✅ |
| HU03 · Facturas con saldo | P0 | ✅ |
| HU04 · Pago parcial y control de concurrencia | P0 | ✅ |
| HU05 · Pasa a vencida sola | P0 | ✅ |
| HU06 · Dashboard = SQL | P0 | ✅ |
| HU07 · Importación CSV con reporte | P1 | ✅ |
| HU08 · Filtrar y exportar CSV | P1 | ✅ |
| HU09 · Anular pago con motivo y auditoría | P1 | ✅ |
| HU10 · Instalable + backend con HTTPS | P1 | 🟡 Todo listo; falta el despliegue en la cuenta AWS |

## Antes de cargar datos reales
- [ ] Desplegar en AWS y completar las verificaciones de `despliegue-aws.md` §6.
- [ ] Ejecutar `backup-verify` en producción y anotarlo en `backup-restore.md`.
- [ ] Probar el instalador en una PC del cliente.
- [ ] Firmar el acuerdo de confidencialidad y tratamiento de datos (spec §11 y §16).
- [ ] Cambiar las credenciales iniciales.
