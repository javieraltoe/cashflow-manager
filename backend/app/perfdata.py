"""Volumen para la prueba de rendimiento (spec §11): 1.000 clientes, 20.000 facturas y
50.000 pagos, generados en PostgreSQL con generate_series (segundos, no minutos).

Reglas que respeta: ningún pago supera el importe (20 % de las facturas quedan pagadas,
el resto con pagos parciales), fechas de pago nunca futuras, montos NUMERIC(15,2).
Uso: python -m app.cli seed-perf --reset   (borra los datos de negocio; nunca en producción)
"""

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

CLIENTS = 1_000
INVOICES = 20_000  # mitad con 2 pagos y mitad con 3 -> 50.000 pagos


def seed_perf(db: Session, today: date, actor_id) -> dict:
    params = {"today": today, "actor": actor_id, "n_clients": CLIENTS, "n_invoices": INVOICES}
    db.execute(text("SELECT setseed(0.42)"))
    db.execute(
        text(
            """
            INSERT INTO clients (id, name, tax_id, is_active)
            SELECT gen_random_uuid(), 'Cliente Perf ' || lpad(g::text, 4, '0'),
                   '30-' || lpad((70000000 + g)::text, 8, '0') || '-0', (g % 25 <> 0)
            FROM generate_series(1, :n_clients) AS g
            """
        ),
        params,
    )
    db.execute(
        text(
            """
            WITH c AS (
                SELECT id, row_number() OVER (ORDER BY name) AS rn FROM clients
                WHERE name LIKE 'Cliente Perf %'
            ), base AS (
                SELECT g,
                       (CAST(:today AS date) - (random() * 720)::int) AS issue,
                       round((10000 + random() * 490000)::numeric, 2) AS amount
                FROM generate_series(1, :n_invoices) AS g
            )
            INSERT INTO invoices (id, client_id, invoice_number, issue_date, due_date, amount,
                                  currency, is_void, created_by)
            SELECT gen_random_uuid(), c.id, 'P-' || lpad(b.g::text, 6, '0'), b.issue,
                   b.issue + (15 + (b.g % 4) * 15), b.amount, 'ARS', false, :actor
            FROM base b JOIN c ON c.rn = ((b.g - 1) % :n_clients) + 1
            """
        ),
        params,
    )
    # k = 2 o 3 pagos por factura. Cada 5ta factura queda saldada (el último pago completa
    # el importe); el resto recibe pagos de importe/(k+1), siempre menores al total.
    db.execute(
        text(
            """
            WITH inv AS (
                SELECT id, amount, issue_date,
                       row_number() OVER (ORDER BY invoice_number) AS n
                FROM invoices WHERE invoice_number LIKE 'P-%'
            ), plan AS (
                SELECT inv.*, CASE WHEN n % 2 = 0 THEN 2 ELSE 3 END AS k FROM inv
            )
            INSERT INTO payments (id, invoice_id, payment_date, amount, method, is_void,
                                  created_by)
            SELECT gen_random_uuid(), p.id,
                   LEAST(p.issue_date + j * 10, CAST(:today AS date)),
                   CASE
                     WHEN p.n % 5 = 0 AND j = p.k
                       THEN p.amount - (p.k - 1) * trunc(p.amount / p.k, 2)
                     WHEN p.n % 5 = 0 THEN trunc(p.amount / p.k, 2)
                     ELSE trunc(p.amount / (p.k + 1), 2)
                   END,
                   (ARRAY['transferencia', 'efectivo', 'cheque', 'tarjeta'])[1 + (j % 4)],
                   false, :actor
            FROM plan p CROSS JOIN LATERAL generate_series(1, p.k) AS j
            """
        ),
        params,
    )
    db.commit()
    db.execute(text("ANALYZE clients; ANALYZE invoices; ANALYZE payments"))
    counts = db.execute(
        text(
            "SELECT (SELECT count(*) FROM clients), (SELECT count(*) FROM invoices), "
            "(SELECT count(*) FROM payments)"
        )
    ).one()
    return {"clients": counts[0], "invoices": counts[1], "payments": counts[2]}
