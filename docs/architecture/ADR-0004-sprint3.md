# ADR-0004 · Decisiones del Sprint 3 (aplicación de escritorio)

Fecha: 2026-10-29 · Estado: aceptada

Alcance (spec §4 y §13): login, clientes, facturas, pagos, mensajes de error e instalador
preliminar. Se suman las pantallas de **saldo a favor** que requiere el ADR-0003 y la
pantalla **Inicio** y **Configuración** de §4. La importación CSV queda para el Sprint 5.

## Decisiones

| # | Decisión | Motivo |
|---|---|---|
| 1 | **Dos capas**: `desktop/app/core` y `desktop/app/services` no importan Qt (config, formatos, cliente HTTP, resumen de Inicio); `desktop/app/views` y `widgets` son PySide6 y solo arman pantallas. | La lógica se prueba sin interfaz gráfica, en el CI y contra la API real. |
| 2 | **`ApiClient`** (httpx) con access y refresh **solo en memoria**: no se guardan en disco. Si el access vence se renueva una vez y se reintenta; si no se puede, `SessionExpired` y se pide volver a ingresar sin perder la pantalla. | §8. Un .exe en una PC compartida no debe dejar sesiones guardadas. |
| 3 | Toda falla se convierte en `ApiError(status, code, message, field)` con el mensaje en español de la API, o uno propio si no hay red o hay timeout (15 s). Los formularios **resaltan el campo** indicado por `field`. | §4 "mensajes de error". Mismo contrato de errores del ADR-0001 #8. |
| 4 | Cada formulario de cobro genera **una `Idempotency-Key` al abrirse** y la reutiliza en cada intento. | ADR-0003 #19: doble clic o reintento tras corte de red no duplica el cobro. |
| 5 | **Sobrepago**: si la API responde `amount_exceeds_balance`, se pregunta si el excedente queda como saldo a favor y, si se confirma, se reenvía con `allow_credit` y la **misma clave**. | ADR-0003 #12: la confirmación es explícita. |
| 6 | Montos: se escriben en formato argentino (`1.234,56`; también se acepta `1234.56`), se convierten a `Decimal` y viajan como string. Se muestran como `$ 1.234,56`. Un punto seguido de 3 dígitos es separador de miles. | §11 formato ARS. Nunca float. |
| 7 | Fechas en pantalla `dd/mm/aaaa`; "hoy" se calcula en **America/Argentina/Buenos_Aires** (`tzdata` incluido porque Windows no trae la base de zonas). La fecha de cobro no puede ser futura (tope en el selector). | §5 zona horaria; ADR-0003 #6. |
| 8 | Llamadas **sincrónicas** con cursor de espera. | Para el MVP en red local o un servidor cercano alcanza y evita la complejidad de hilos. Si un cliente trabaja con mucha latencia, se pasa a `QThreadPool`. |
| 9 | **Inicio** muestra conteos (vencidas, vencen en 7 días, clientes activos) y los próximos vencimientos usando los endpoints existentes; los montos agregados quedan para `/metrics` (Sprint 4). Botón para abrir el dashboard web. | §4 "totales esenciales y próximos vencimientos" sin adelantar el Sprint 4. |
| 10 | Las acciones de administrador (anular factura, pago o cobro a cuenta; usuarios) **solo se muestran** al rol admin. El permiso real lo sigue verificando la API. | §3 y HU01. La interfaz no es una barrera de seguridad. |
| 11 | Configuración local en `%APPDATA%\CashFlowManager\config.json`: URL del servidor, URL del dashboard y último email. La URL se normaliza (`servidor:8000` → `http://servidor:8000/api/v1`) y se avisa si es **http hacia otra PC**. | §15 "configuración de URL del servidor". |
| 12 | **Instalador preliminar**: PyInstaller en modo carpeta (`onedir`, arranca más rápido que `onefile` y da menos falsos positivos de antivirus), zip portable y, si está Inno Setup 6.3+, un instalador **por usuario** (sin permisos de administrador). Sin firma digital todavía. | §13 Sprint 3. La firma queda para el Sprint 5 ("instalador firmado si aplica"). |
| 13 | Tests de interfaz **offscreen** (`desktop/tests/test_ui_smoke.py`) contra la API real: corren donde PySide6 está instalado y se saltean en el CI. Los mensajes modales se reemplazan por un registro. | Cubren login, todas las páginas, formularios, sobrepago, doble clic, anulaciones y saldo a favor sin intervención manual. |

## Pendiente
- Pruebas de usabilidad con un usuario real y ajustes de tamaños y atajos.
- Firma de código del ejecutable y del instalador (Sprint 5).
- Si se necesita trabajar con mucha latencia: llamadas en segundo plano (`QThreadPool`).
