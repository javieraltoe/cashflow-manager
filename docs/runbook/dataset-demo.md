# Dataset de demostración reconciliado (HU06)

```powershell
.\scripts\dev.ps1 seed-demo          # base sin clientes
.\scripts\dev.ps1 seed-demo reset    # BORRA clientes, facturas, pagos y créditos (no usuarios)
# o dentro de Docker:
docker compose exec api python -m app.cli seed-demo
```

Requiere un administrador creado (`create-admin`). Las fechas son **relativas al día de
carga** (T = hoy en Buenos Aires; Mk = día 1 del mes de hace k meses), por eso los valores
esperados son **siempre los mismos**. El test `backend/tests/test_metrics_hu06.py` lo
verifica cargando el dataset un 1° de mes, un 31/12, en enero y un 29/02.

## Casos

| Factura | Cliente | Importe | Vence | Pagos | Saldo | Estado / caso |
|---|---|---:|---|---|---:|---|
| F-1001 | Almacén Don Pepe | 100.000 | T−10 | 30.000 transferencia (T) | 70.000 | Vencida 10 d, pago parcial |
| F-2001 | Constructora Andina SA | 250.000 | T−45 | — | 250.000 | Vencida 45 d |
| F-2002 | Constructora Andina SA | 80.000 | T−75 | 20.000 cheque (T) | 60.000 | Vencida 75 d, parcial |
| F-3001 | Distribuidora Norte SRL | 150.000 | T−120 | — | 150.000 | Vencida 120 d |
| F-6001 | Gráfica del Sur (inactivo) | 45.000 | T−200 | — | 45.000 | Vencida 200 d, cliente inactivo |
| F-4001 | Estudio Contable Ríos | 60.000 | T+3 | — | 60.000 | Pendiente, vence en 3 d |
| F-5001 | Farmacia Central | 90.000 | T+6 | 40.000 efectivo (T) | 50.000 | Parcial, vence en 6 d |
| F-1002 | Almacén Don Pepe | 120.000 | T+20 | 5.000 **saldo a favor** (T) | 115.000 | Imputación de crédito |
| F-3002 | Distribuidora Norte SRL | 30.000 | **T** | — | 30.000 | Vence hoy: **no** vencida |
| F-4002 | Estudio Contable Ríos | 70.000 | T+10 | — | — | **Anulada**: no cuenta |
| F-5002 | Farmacia Central | 50.000 | T−5 | 50.000 cheque **anulado** (T) | 50.000 | Vencida 5 d, pago anulado |
| F-7001 | Hotel Las Lomas | 200.000 | T−15 | 200.000 + **10.000 de excedente** (T) | 0 | Pagada con saldo a favor |
| H-01…H-05 | Hotel Las Lomas | ver abajo | Mk−1 | total el día Mk | 0 | Historial mensual |

Además: **cobro a cuenta** de Almacén Don Pepe por 15.000 en efectivo (T).
Historial: H-01 300.000 (hace 1 mes) · H-02 220.000 · H-03 180.000 · H-04 260.000 · H-05 150.000.

## Valores esperados

| Indicador | Valor | Cómo se compone |
|---|---:|---|
| Saldo total por cobrar | **$ 880.000,00** | Suma de saldos de facturas no anuladas |
| Saldo vencido | **$ 625.000,00** | 70.000 + 250.000 + 60.000 + 150.000 + 45.000 + 50.000 |
| % vencido | **71,02 %** | 625.000 / 880.000 |
| Facturas vencidas | **6** | F-3002 vence hoy y no cuenta |
| Próximos 7 días | **$ 140.000,00** (3) | F-3002 30.000 + F-4001 60.000 + F-5001 50.000 |
| Saldo a favor disponible | **$ 20.000,00** | (10.000 + 15.000) − 5.000 imputados |
| Cobrado en el mes en curso | **$ 315.000,00** | Pagos 290.000 (sin el anulado ni el "saldo a favor") + créditos 25.000 |
| Cobrado últimos 12 meses | **$ 1.425.000,00** | 315.000 + 300.000 + 220.000 + 180.000 + 260.000 + 150.000 |
| Aging 1–30 | $ 120.000,00 (2) | F-1001 + F-5002 |
| Aging 31–60 | $ 250.000,00 (1) | F-2001 |
| Aging 61–90 | $ 60.000,00 (1) | F-2002 |
| Aging 91+ | $ 195.000,00 (2) | F-3001 + F-6001 |

Top deudores: Constructora Andina SA 310.000 · Almacén Don Pepe 185.000 · Distribuidora
Norte SRL 180.000 · Farmacia Central 100.000 · Estudio Contable Ríos 60.000 · Gráfica del Sur 45.000.

## Verificación manual con SQL (HU06)

```powershell
docker compose exec db psql -U cashflow -d cashflow
```

```sql
-- Saldo por factura vigente (base de todas las consultas)
CREATE TEMP VIEW saldos AS
SELECT i.id, i.client_id, i.due_date, i.amount - COALESCE(p.paid, 0) AS balance
FROM invoices i
LEFT JOIN (SELECT invoice_id, SUM(amount) AS paid FROM payments
           WHERE NOT is_void GROUP BY invoice_id) p ON p.invoice_id = i.id
WHERE NOT i.is_void;

SELECT SUM(balance) AS por_cobrar FROM saldos;                                   -- 880000.00
SELECT SUM(balance), COUNT(*) FROM saldos
 WHERE due_date < CURRENT_DATE AND balance > 0;                                  -- 625000.00 | 6
SELECT SUM(balance), COUNT(*) FROM saldos
 WHERE due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7 AND balance > 0;       -- 140000.00 | 3
SELECT (SELECT COALESCE(SUM(amount), 0) FROM payments
         WHERE NOT is_void AND method <> 'saldo_a_favor'
           AND payment_date >= date_trunc('month', CURRENT_DATE))
     + (SELECT COALESCE(SUM(amount), 0) FROM client_credits
         WHERE NOT is_void AND credit_date >= date_trunc('month', CURRENT_DATE))
       AS cobrado_mes;                                                            -- 315000.00
```

> `CURRENT_DATE` usa la zona de la sesión de PostgreSQL (UTC). Entre las 21:00 y las
> 24:00 de Argentina ya es "mañana" en UTC: para comparar en ese horario, reemplazá
> `CURRENT_DATE` por `(now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date`.
