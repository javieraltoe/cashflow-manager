# Prueba de rendimiento (spec §11)

Objetivo: pantallas y KPIs frecuentes **< 3 s** con 1.000 clientes, 20.000 facturas y
50.000 pagos.

## Cómo reproducirla

```powershell
.\scripts\dev.ps1 up
.\scripts\dev.ps1 seed-perf reset      # BORRA los datos de negocio y carga el volumen (~3 s)
.\scripts\dev.ps1 bench admin@miempresa.com.ar
```

El script hace login, calienta cada consulta y la mide 7 veces por HTTP (igual que el
dashboard y el escritorio). Termina con error si algún p95 supera 3 s.

El volumen respeta las reglas de negocio: 4.000 facturas saldadas y 16.000 con saldo,
ningún saldo negativo y ninguna fecha de pago futura.

## Resultado de referencia (2026-10-29)

Entorno: contenedor Linux de 2 vCPU, PostgreSQL 16 local, API con uvicorn (1 proceso),
sin Docker. En una PC con Docker Desktop los tiempos pueden ser algo mayores.

| Consulta | Mediana (ms) | p95 (ms) |
|---|---:|---:|
| KPIs (overview) | 78 | 82 |
| Serie mensual 12 meses | 31 | 37 |
| Antigüedad (aging) | 68 | 85 |
| Top 10 deudores | 63 | 91 |
| Próximos 7 días | 110 | 132 |
| Facturas: 1ra página | 76 | 81 |
| Facturas vencidas | 132 | 206 |
| Facturas: búsqueda por número | 189 | 212 |
| Clientes: búsqueda | 12 | 15 |
| Pagos: 1ra página | 626 | 647 |

**Peor p95: 647 ms → cumple el objetivo con margen (4,6 veces por debajo de 3 s).**

El dashboard completo hace 5 consultas de métricas: unos 350 ms en total en este entorno.

## Observaciones

- La consulta más lenta es el listado de pagos: calcula el saldo de la factura de cada
  fila sumando los pagos de **todas** las facturas. Si con datos reales supera ~1 s, se
  puede limitar esa suma a las facturas de la página.
- Todas las métricas son agregaciones en SQL con los índices del §7; no hay tablas
  resumen que se puedan desincronizar.
