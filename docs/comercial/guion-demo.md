# Guion de demostración (15 minutos)

Objetivo: mostrar en vivo, con datos de ejemplo, cómo el cliente pasa de planillas sueltas
a ver su cobranza en minutos (spec §1). Sirve también como guion para grabar un video.

## Preparación (el día anterior)

```powershell
.\scripts\dev.ps1 up
.\scripts\dev.ps1 seed-demo reset        # 7 clientes y 17 facturas de ejemplo
```
- Usuarios: `admin@demo.com.ar` (administrador) y uno operador.
- Tener a mano `docs/manual/plantilla-demo.csv` (o la plantilla descargada desde la app)
  con 3 filas, una con error.
- Cerrar notificaciones y aumentar el tamaño de letra de Windows al 125 %.

## Guion

| Min | Pantalla | Qué mostrar | Qué decir |
|---|---|---|---|
| 0-1 | — | Problema | "Hoy las cuentas a cobrar están en planillas: nadie sabe con certeza cuánto se debe ni qué vence." |
| 1-3 | Escritorio → Inicio | Tarjetas: $ 880.000 por cobrar, $ 625.000 vencido, $ 140.000 en 7 días | "Al abrir la app ya ven lo urgente." Doble clic en una factura que vence. |
| 3-5 | Facturas | Filtrar *Vencida*; abrir F-2001 (45 días de mora) | "El estado cambia solo cuando vence: nadie tiene que acordarse." |
| 5-7 | Registrar pago | Cobrar $ 100.000 de F-2001 → saldo $ 150.000, estado *Vencida* | "El saldo es exacto al centavo." Intentar cobrar $ 200.000: aparece la pregunta de saldo a favor → *No*. |
| 7-8 | Anular pago (admin) | Anular el pago con motivo "cheque rechazado" | "Nada se borra: queda quién, cuándo y por qué." |
| 8-10 | Importar CSV | Elegir el archivo: 2 OK y 1 con error explicado; importar | "Pasan de Excel en un minuto, sin cargar a mano." |
| 10-13 | Dashboard web | KPIs, cobranza mensual, aging, deudores; filtrar *Constructora Andina SA* | "Lo mismo, desde cualquier navegador, para el dueño o el contador." Exportar CSV. |
| 13-14 | Operador | Ingresar como operador: no ve *Usuarios* ni *Anular* | "Cada uno ve y hace lo que le corresponde." |
| 14-15 | Cierre | Seguridad, backups diarios cifrados, instalación | "Instalación en una PC en 5 minutos; los datos quedan en un servidor seguro con copias diarias." |

## Preguntas frecuentes

- **¿Funciona sin Internet?** No en esta versión: la app trabaja contra el servidor (spec §2).
- **¿Factura electrónica AFIP/ARCA?** No; los números de factura son referencias. Es una
  ampliación posible (spec §2 y §16).
- **¿Cuántos usuarios?** Pensado para 1 a 10 administrativos simultáneos.
- **¿Dólares?** Esta versión trabaja en pesos (ARS).

## Demo a distancia (link temporal, sin costo)

Para que el cliente pruebe desde su PC sin desplegar en AWS: Cloudflare Tunnel en modo
rápido (sin cuenta) publica el dashboard de tu PC en `https://<al-azar>.trycloudflare.com`,
con certificado válido.

```powershell
winget install Cloudflare.cloudflared     # una sola vez
.\scripts\dev.ps1 up
.\scripts\dev.ps1 seed-demo reset         # SOLO datos de ejemplo: el link es público
.\scripts\dev.ps1 demo-link               # muestra el link; Ctrl+C lo cierra
```

- El cliente entra con un **usuario demo operador** (nunca con un administrador real).
- Solo se publica el dashboard: la API, la base y Swagger siguen cerrados.
- El link cambia cada vez y funciona mientras la PC y la ventana estén abiertas.
- Al terminar: Ctrl+C y desactivar el usuario demo (Configuración → Usuarios).
