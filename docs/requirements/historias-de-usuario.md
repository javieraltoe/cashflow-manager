# Historias de usuario · CashFlow Manager MVP

Fuente: *CashFlow Manager — Especificación MVP v1.0* (texto provisto por el responsable del
producto el 2026-10-29). La especificación completa todavía no está versionada en el repo.

## Estado por sprint

| HU | Prioridad | Historia | Sprint | Estado |
|---|---|---|---|---|
| HU01 | P0 | Login y roles | 1 | Hecha |
| HU02 | P0 | Clientes | 1 | Hecha |
| HU03 | P0 | Facturas con saldo | 1 | Hecha |
| HU04 | P0 | Pago parcial con saldo exacto, sin pagar más de lo adeudado, con control de concurrencia | 2 | Hecha |
| HU05 | P0 | Una factura impaga pasa a vencida sola | 1 | Hecha |
| HU06 | P0 | El dashboard coincide con las sumas en SQL | 4 | Hecha (`test_metrics_hu06.py`, `docs/runbook/dataset-demo.md`) |
| HU07 | P1 | Importación de CSV | 5 | Hecha (`test_imports_api.py`) |
| HU08 | P1 | Filtros y exportación a CSV | 5 | Hecha (`test_exports_api.py`) |
| HU09 | P1 | Anular un pago con motivo; el saldo vuelve a subir y queda auditado | 2 | Hecha |
| HU10 | P1 | Instalador y despliegue con HTTPS | 5 | Lista para desplegar (`docs/runbook/despliegue-aws.md`) |

## HU04 (P0, imprescindible)

> “Registro un pago parcial; el saldo baja exactamente y no puedo pagar más de lo adeudado.”

Si una factura es de $1.000 y registro un pago de $400, el saldo tiene que quedar
exactamente en $600,00, sin errores de redondeo. Si después intento registrar $700, el
sistema lo rechaza porque supera lo que se debe. Esto incluye el control de concurrencia:
si dos personas registran un pago sobre la misma factura en el mismo momento, entre las
dos tampoco pueden pasarse del saldo.

## HU09 (P1, importante)

> “Anulo un pago con motivo; vuelve a aumentar el saldo y queda auditado.”

Si un pago se cargó por error, el administrador lo anula indicando un motivo, por ejemplo
“cheque rechazado”. El pago no se borra: queda marcado como anulado, el saldo de la factura
vuelve a subir y queda registrado quién lo anuló, cuándo y por qué.

## Auditoría

Es el registro de quién hizo qué y cuándo. Existe desde el Sprint 1 para clientes y
facturas; en el Sprint 2 se extiende a los pagos.
