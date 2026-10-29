"""Mide el tiempo de respuesta de la API (spec §11: pantallas y KPIs frecuentes < 3 s).

Uso (con la API levantada y datos cargados con seed-perf):
    python scripts/seed/bench_metrics.py --email admin@miempresa.com.ar
    python scripts/seed/bench_metrics.py --url http://localhost:8000/api/v1 --runs 10

Hace login, calienta cada endpoint una vez y después mide N veces. Informa mediana, p95 y
máximo en milisegundos, y termina con código 1 si algún p95 supera el objetivo.
"""

import argparse
import getpass
import statistics
import sys
import time

import httpx

TARGET_MS = 3000

ENDPOINTS = [
    ("KPIs (overview)", "/metrics/overview", {}),
    ("Serie mensual 12 meses", "/metrics/collections-monthly", {}),
    ("Antigüedad (aging)", "/metrics/aging", {}),
    ("Top 10 deudores", "/metrics/top-debtors", {}),
    ("Próximos 7 días", "/metrics/upcoming", {}),
    ("Facturas: 1ra página", "/invoices", {"page_size": 50}),
    ("Facturas vencidas", "/invoices", {"status": "VENCIDA", "page_size": 50}),
    ("Facturas: búsqueda por número", "/invoices", {"q": "P-0199", "page_size": 50}),
    ("Clientes: búsqueda", "/clients", {"q": "perf 05", "page_size": 50}),
    ("Pagos: 1ra página", "/payments", {"page_size": 50}),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:8000/api/v1")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", help="Si no se indica, se pide sin mostrarla")
    parser.add_argument("--runs", type=int, default=7)
    args = parser.parse_args()
    password = args.password or getpass.getpass("Contraseña: ")

    with httpx.Client(base_url=args.url.rstrip("/"), timeout=60) as http:
        resp = http.post("/auth/login", json={"email": args.email, "password": password})
        if resp.status_code != 200:
            print(f"Login falló: {resp.status_code} {resp.text}", file=sys.stderr)
            return 1
        http.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"
        print(f"{'Consulta':34} {'mediana':>9} {'p95':>9} {'máx':>9}  (ms, {args.runs} corridas)")
        worst = 0.0
        for label, path, params in ENDPOINTS:
            http.get(path, params=params).raise_for_status()  # calentamiento
            times = []
            for _ in range(args.runs):
                start = time.perf_counter()
                http.get(path, params=params).raise_for_status()
                times.append((time.perf_counter() - start) * 1000)
            times.sort()
            p95 = times[min(len(times) - 1, round(0.95 * (len(times) - 1)))]
            worst = max(worst, p95)
            print(f"{label:34} {statistics.median(times):9.0f} {p95:9.0f} {times[-1]:9.0f}")
    verdict = "OK" if worst < TARGET_MS else "SUPERA EL OBJETIVO"
    print(f"\nPeor p95: {worst:.0f} ms · objetivo < {TARGET_MS} ms · {verdict}")
    return 0 if worst < TARGET_MS else 1


if __name__ == "__main__":
    sys.exit(main())
