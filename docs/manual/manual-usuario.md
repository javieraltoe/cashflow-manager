# CashFlow Manager · Manual de uso

Para el personal administrativo que registra facturas y cobranzas. Lectura: 10 minutos.

## 1. Instalar e ingresar

1. Ejecutá `CashFlowManager-Setup-1.0.0.exe` (no pide permisos de administrador).
2. Abrí **CashFlow Manager** desde el menú Inicio.
3. En el ingreso completá:
   - **Servidor**: la dirección que te dio tu administrador (ej. `https://cobranzas.miempresa.com.ar`).
   - **Email** y **contraseña** de tu usuario.
4. Si te dieron una contraseña inicial, cambiala en **Configuración → Cambiar contraseña**.

> Después de 5 intentos fallidos el ingreso se bloquea 15 minutos. La sesión se renueva sola
> mientras trabajás; si pasan varios días te pide ingresar de nuevo.

## 2. Pantallas

| Pantalla | Para qué |
|---|---|
| **Inicio** | Saldo por cobrar, vencido y lo que vence en 7 días; próximos vencimientos (doble clic abre la factura) |
| **Clientes** | Buscar, crear, editar y desactivar clientes |
| **Facturas** | Cargar y editar facturas, ver su saldo y estado, registrar pagos, exportar a CSV |
| **Pagos** | Consultar cobros por fecha, cliente o medio |
| **Saldo a favor** | Anticipos y excedentes de cada cliente; imputarlos a facturas |
| **Importar CSV** | Cargar muchas facturas desde un archivo |
| **Configuración** | Tu perfil, contraseña y, si sos administrador, los usuarios |

**F5** actualiza la pantalla. El botón **Abrir dashboard web** muestra los indicadores y gráficos.

## 3. Tareas frecuentes

**Cargar una factura**: Facturas → *Nueva factura* → cliente, número, fechas, importe
(`125.000,50`) → Guardar. El número no puede repetirse para el mismo cliente.

**Registrar un cobro**: Facturas → elegí la factura → *Registrar pago* → importe recibido,
medio, fecha y referencia (nº de transferencia o cheque). El saldo se actualiza al instante.
- Si el importe es **mayor** al saldo, el sistema pregunta si el excedente queda como
  **saldo a favor** del cliente. Si fue un error de tipeo, respondé *No* y corregí.
- Un doble clic no duplica el cobro.

**Usar un saldo a favor**: Saldo a favor → elegí el cliente → *Imputar a factura*.

**Anticipo sin factura**: Saldo a favor → cliente → *Cobro a cuenta*.

**Anular un pago** (solo administrador; por ejemplo, un cheque rechazado): Facturas →
*Ver detalle y pagos* → elegí el pago → *Anular pago* → motivo. El saldo de la factura
vuelve a subir y queda registrado quién, cuándo y por qué. No se puede deshacer.

**Estados de una factura**: *Pendiente* (sin cobros), *Parcial* (con cobros, no vencida),
*Vencida* (pasó el vencimiento con saldo; cambia sola), *Pagada*, *Anulada*.

## 4. Importar facturas desde Excel

1. Importar CSV → **Descargar plantilla** y completala en Excel con estas columnas:
   `client_name, invoice_number, issue_date, due_date, amount, description`.
   - Fechas como `2026-10-30` (año-mes-día). Importe sin separador de miles: `125000.50`.
2. En Excel: **Archivo → Guardar como → CSV UTF-8 (delimitado por comas)**.
3. **Elegir archivo…**: el sistema muestra cada fila con *OK* o el error exacto.
   Nada se guarda todavía.
4. Si hay clientes nuevos, marcá *Crear los clientes que no existan* (o crealos antes).
5. **Importar N facturas válidas**. Las filas con error no se cargan: corregilas y volvé a
   importar el mismo archivo; las ya cargadas se rechazan como "ya existe", sin duplicarse.

Límites: 5 MB y 5.000 filas por archivo.

## 5. Exportar

- **Facturas → Exportar CSV**: exporta todas las facturas que cumplen los filtros actuales.
- En el **dashboard web**, cada gráfico tiene su botón *Exportar CSV*.

## 6. Dashboard web

Abrilo desde Inicio o en el navegador (`https://cobranzas.miempresa.com.ar`) con el mismo
usuario. Los indicadores **"A hoy"** (saldo, vencido, próximos 7 días) no cambian con el
período; los **"Del período"** (cobrado) sí. Filtrá por cliente desde la barra lateral.

## 7. Problemas comunes

| Mensaje | Qué hacer |
|---|---|
| "No se pudo conectar con el servidor" | Revisá Internet y la dirección del servidor; si sigue, avisá a soporte |
| "Tu sesión venció" | Volvé a ingresar; no se pierde lo que estabas viendo |
| "Demasiados intentos fallidos" | Esperá 15 minutos o pedí al administrador que restablezca tu contraseña |
| Windows avisa "editor desconocido" al instalar | Solo si la versión no está firmada: *Más información → Ejecutar de todas formas* |
| El campo queda en rojo | El mensaje debajo explica qué corregir |

Soporte: _completar con el contacto acordado en la propuesta comercial_.
