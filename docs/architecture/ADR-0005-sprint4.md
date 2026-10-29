# ADR-0005 · Decisiones del Sprint 4 (indicadores y dashboard)

Fecha: 2026-10-29 · Estado: aceptada

Alcance (spec §4, §6, §9 y §13): endpoints `/metrics`, dashboard Streamlit con filtros,
dataset semilla reconciliado (**HU06**) y la prueba de rendimiento del §11.

## Decisiones

| # | Decisión | Motivo |
|---|---|---|
| 1 | Cinco endpoints: `GET /metrics/overview`, `/collections-monthly`, `/aging`, `/top-debtors` y `/upcoming`. Los puede consultar **cualquier usuario autenticado**. | §9 y §3: el operador también consulta el dashboard. |
| 2 | Todo se calcula con **agregaciones SQL en cada consulta** (saldo = importe − pagos vigentes), sin tablas resumen. | Una sola definición de saldo, la misma que usan facturas y pagos (ADR-0002 #10). Rendimiento medido: peor p95 = 647 ms con el volumen del §11. |
| 3 | **Stock "a hoy"** (por cobrar, vencido, % vencido, próximos 7 días, aging, deudores, saldo a favor) y **flujo "del período"** (cobrado, serie mensual). El dashboard los muestra en dos bloques rotulados. | §6: los KPIs de stock son a fecha actual hasta que haya snapshots. |
| 4 | **Cobrado** = pagos vigentes sin método `saldo_a_favor` + saldo a favor recibido (excedentes y cobros a cuenta) por su fecha. Se muestra también el desglose. | ADR-0003 #18: cada peso que entra se cuenta una vez. **Difiere de la fórmula literal del §6** ("SUM(pagos no anulados)"), que contaría dos veces las imputaciones de saldo a favor. |
| 5 | **% vencido = null** cuando no hay saldo por cobrar; la interfaz muestra "N/D". | §6: "si el denominador es 0, mostrar 0 o N/D". |
| 6 | Período por defecto: **últimos 12 meses** incluido el actual; máximo 5 años. La serie mensual devuelve **todos los meses** del período (0 si no hubo cobros). | Un gráfico sin huecos ni meses faltantes. |
| 7 | Filtro por cliente aplicado a **todos** los indicadores. | §4: filtros por rango temporal y cliente. |
| 8 | **Dataset demo con fechas relativas a hoy** (`python -m app.cli seed-demo`): los KPIs esperados son siempre los mismos y están documentados en `docs/runbook/dataset-demo.md`. HU06 se verifica en tres partes iguales: **valores documentados = API = SQL escrito a mano**. | HU06 y §13 Sprint 4 "dataset semilla reconciliado". |
| 9 | `seed-perf` genera el volumen del §11 con `generate_series` (unos 3 s). `seed-demo --reset` y `seed-perf --reset` **se niegan en producción**. | §11: prueba medida y documentada (`docs/runbook/rendimiento.md`). |
| 10 | **Dashboard**: login con el mismo usuario de la app. Los tokens se guardan en la sesión de Streamlit **del servidor** y se renuevan solos; el navegador nunca ve la base ni los tokens. | §8: el dashboard solo usa endpoints protegidos de la API. |
| 11 | Gráficos Plotly de **una serie y un solo color**, sin leyenda, barras finas de puntas redondeadas, separadores argentinos y tooltip con el monto exacto. Cada gráfico tiene su tabla equivalente. | Legibilidad y accesibilidad (la tabla no depende del color). |
| 12 | **Exportación CSV de la vista filtrada** en el dashboard (cobranza mensual, aging, deudores y próximos vencimientos): coma como separador, punto decimal, UTF-8 con BOM para Excel. | §4 "Exportación CSV de vista filtrada". El endpoint `/exports/invoices.csv` (HU08) queda para el Sprint 5. |
| 13 | La pantalla **Inicio del escritorio** pasa a mostrar montos usando `/metrics`: los mismos números que el dashboard. | Completa el ADR-0004 #9. |

## Pendiente
- Snapshots históricos para ver el stock a una fecha pasada (fuera del MVP según §6).
- Optimizar el listado de pagos si con datos reales supera ~1 s (ver `rendimiento.md`).
