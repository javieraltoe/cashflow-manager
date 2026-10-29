# Sprint 4 · Verificación de indicadores y dashboard

Ejecutar en PowerShell desde la raíz del repo, con Docker Desktop abierto.

## 1. Tests

```powershell
.\scripts\dev.ps1 setup
.\scripts\dev.ps1 up                 # reconstruye api y dashboard
.\scripts\dev.ps1 lint               # All checks passed!
.\scripts\dev.ps1 test
```

Con Docker arriba y las dependencias del `.venv` (PySide6 y Streamlit) todo tiene que dar
verde: **`305 passed`, 0 saltados** (en el CI, sin PySide6: `280 passed, 1 skipped`). Incluye:
- `backend/tests/test_metrics_hu06.py`: HU06 (documentado = API = SQL) y bordes de los rangos.
- `dashboard/tests/`: formatos, datos, exportaciones CSV, gráficos y la app Streamlit
  completa ejecutada con `streamlit.testing` (login, KPIs, filtro por cliente).

## 2. HU06 a mano (10 minutos)

```powershell
.\scripts\dev.ps1 seed-demo reset     # borra datos de negocio y carga el dataset demo
```

1. Abrí <http://localhost:8501> e ingresá con tu usuario.
2. Compará con `docs/runbook/dataset-demo.md`:

| Tarjeta | Esperado | ✔ |
|---|---|---|
| Saldo total por cobrar | $ 880.000 | ☐ |
| Saldo vencido | $ 625.000 | ☐ |
| % vencido | 71,02 % | ☐ |
| Facturas vencidas | 6 | ☐ |
| Vence en 7 días | $ 140.000 | ☐ |
| Saldo a favor disponible | $ 20.000 | ☐ |
| Cobrado (últimos 12 meses) | $ 1.425.000 | ☐ |

3. Cambiá el período al mes en curso: **Cobrado = $ 315.000**; las tarjetas "A hoy" no cambian.
4. Elegí el cliente *Constructora Andina SA*: por cobrar $ 310.000 y 100,00 % vencido.
5. Ejecutá las consultas SQL de `dataset-demo.md` en `psql`: tienen que dar lo mismo.
6. Probá los botones **Exportar CSV** y abrí uno en Excel.
7. En el escritorio (`.\scripts\dev.ps1 desktop`), Inicio muestra los mismos montos.

## 3. Rendimiento (§11)

```powershell
.\scripts\dev.ps1 seed-perf reset
.\scripts\dev.ps1 bench admin@miempresa.com.ar     # esperado: "Peor p95 ... OK"
```

Anotá tus resultados en `docs/runbook/rendimiento.md` (hay una tabla de referencia).

## 4. Volver a datos limpios

```powershell
.\scripts\dev.ps1 seed-demo reset     # o reset-db para borrar todo, usuarios incluidos
```
