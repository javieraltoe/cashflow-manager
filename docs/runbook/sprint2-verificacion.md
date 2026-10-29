# Sprint 2 · Verificación de criterios de aceptación

Ejecutar en PowerShell desde la raíz del repo, con Docker Desktop abierto.

## 1. Reconstruir la API

```powershell
.\scripts\dev.ps1 up             # reconstruye la imagen de la API (aplica las migraciones 0002 y 0003)
.\scripts\dev.ps1 logs api       # debe aparecer: Running upgrade 0001 -> 0002 y 0002 -> 0003  (Ctrl+C para salir)
```

En <http://localhost:8000/docs> tienen que aparecer las secciones **payments** y **credits**.

## 2. Pruebas automáticas

```powershell
.\scripts\dev.ps1 lint           # All checks passed!
.\scripts\dev.ps1 test           # 167 passed  (con Docker arriba)
```

Sin Docker el resultado esperado es `47 passed, 120 skipped`.

## 3. Prueba manual de la API (PowerShell)

Necesita un administrador (ver Sprint 1, paso 3).

```powershell
$B = "http://localhost:8000/api/v1"
$login = Invoke-RestMethod -Method Post "$B/auth/login" -ContentType "application/json" `
  -Body (@{ email = "admin@miempresa.com.ar"; password = "TU_CLAVE" } | ConvertTo-Json)
$H = @{ Authorization = "Bearer $($login.access_token)" }

$c = Invoke-RestMethod -Method Post "$B/clients" -Headers $H -ContentType "application/json" `
  -Body (@{ name = "Cobros SA" } | ConvertTo-Json)
$f = Invoke-RestMethod -Method Post "$B/invoices" -Headers $H -ContentType "application/json" `
  -Body (@{ client_id = $c.id; invoice_number = "P-0001"; issue_date = "2026-10-01";
            due_date = "2026-11-30"; amount = "125000.50" } | ConvertTo-Json)

# HU04: pago parcial
$p1 = Invoke-RestMethod -Method Post "$B/payments" -Headers $H -ContentType "application/json" `
  -Body (@{ invoice_id = $f.id; amount = "25000.50"; method = "transferencia"; reference = "TRF 1" } | ConvertTo-Json)
$p1 | Select-Object amount, invoice_balance, invoice_status      # 100000.00 · PARCIAL

# HU04: pago mayor al saldo -> 409
try {
  Invoke-RestMethod -Method Post "$B/payments" -Headers $H -ContentType "application/json" `
    -Body (@{ invoice_id = $f.id; amount = "100000.01"; method = "efectivo" } | ConvertTo-Json)
} catch { $_.ErrorDetails.Message }   # {"error":{"code":"amount_exceeds_balance",...}}

# HU04: pago total
$p2 = Invoke-RestMethod -Method Post "$B/payments" -Headers $H -ContentType "application/json" `
  -Body (@{ invoice_id = $f.id; amount = "100000.00"; method = "efectivo" } | ConvertTo-Json)
$p2 | Select-Object invoice_balance, invoice_status              # 0.00 · PAGADA

# Anulación por administrador, con motivo
$v = Invoke-RestMethod -Method Post "$B/payments/$($p2.id)/void" -Headers $H -ContentType "application/json" `
  -Body (@{ reason = "Cheque rechazado" } | ConvertTo-Json)
$v | Select-Object is_void, void_reason, invoice_balance, invoice_status   # True · 100000.00 · PARCIAL

# Idempotencia: el mismo envío dos veces con la misma clave -> un solo pago
$HK = $H + @{ "Idempotency-Key" = [guid]::NewGuid().ToString() }
$body = @{ invoice_id = $f.id; amount = "10.00"; method = "efectivo" } | ConvertTo-Json
(Invoke-WebRequest -UseBasicParsing -Method Post "$B/payments" -Headers $HK -ContentType "application/json" -Body $body).StatusCode   # 201
(Invoke-WebRequest -UseBasicParsing -Method Post "$B/payments" -Headers $HK -ContentType "application/json" -Body $body).StatusCode   # 200 (repetido)

# Historial de la factura (incluye anulados)
(Invoke-RestMethod "$B/payments?invoice_id=$($f.id)&include_void=true" -Headers $H).total   # 3

# Saldo a favor: sobrepago confirmado + cobro a cuenta + imputación manual
$f2 = Invoke-RestMethod -Method Post "$B/invoices" -Headers $H -ContentType "application/json" `
  -Body (@{ client_id = $c.id; invoice_number = "P-0002"; issue_date = "2026-10-01";
            due_date = "2026-11-30"; amount = "1000.00" } | ConvertTo-Json)
$f3 = Invoke-RestMethod -Method Post "$B/invoices" -Headers $H -ContentType "application/json" `
  -Body (@{ client_id = $c.id; invoice_number = "P-0003"; issue_date = "2026-10-01";
            due_date = "2026-11-30"; amount = "500.00" } | ConvertTo-Json)
try {   # sin confirmar -> 409, el mensaje informa el excedente
  Invoke-RestMethod -Method Post "$B/payments" -Headers $H -ContentType "application/json" `
    -Body (@{ invoice_id = $f2.id; amount = "1100.00"; method = "transferencia" } | ConvertTo-Json)
} catch { $_.ErrorDetails.Message }   # amount_exceeds_balance ... allow_credit
$p3 = Invoke-RestMethod -Method Post "$B/payments" -Headers $H -ContentType "application/json" `
  -Body (@{ invoice_id = $f2.id; amount = "1100.00"; method = "transferencia"; allow_credit = $true } | ConvertTo-Json)
$p3 | Select-Object amount, credit_amount, invoice_status          # 1000.00 · 100.00 · PAGADA

$a = Invoke-RestMethod -Method Post "$B/credits" -Headers $H -ContentType "application/json" `
  -Body (@{ client_id = $c.id; amount = "300.00"; method = "efectivo"; reference = "Anticipo" } | ConvertTo-Json)
$a.client_available                                               # 400.00

$i = Invoke-RestMethod -Method Post "$B/credits/apply" -Headers $H -ContentType "application/json" `
  -Body (@{ invoice_id = $f3.id; amount = "350.00" } | ConvertTo-Json)
$i | Select-Object method, invoice_balance, invoice_status        # saldo_a_favor · 150.00 · PARCIAL
Invoke-RestMethod "$B/clients/$($c.id)/credit" -Headers $H        # credited 400.00 · applied 350.00 · available 50.00

# Anular el pago cuyo excedente ya se usó -> bloqueado
try {
  Invoke-RestMethod -Method Post "$B/payments/$($p3.id)/void" -Headers $H -ContentType "application/json" `
    -Body (@{ reason = "Transferencia rechazada" } | ConvertTo-Json)
} catch { $_.ErrorDetails.Message }   # {"error":{"code":"credit_in_use",...}}
```

## 4. Checklist

| HU | Criterio | Cómo se verifica | ✔ |
|---|---|---|---|
| HU04 | Factura de $1.000, pago de $400 → saldo $600,00 exacto; un pago de $700 se rechaza | `test_hu04_pago_parcial_exacto_y_no_se_paga_mas_de_lo_adeudado` | ☐ |
| HU09 | Anular con motivo "cheque rechazado": el pago no se borra, el saldo sube y queda quién, cuándo y por qué | `test_hu09_anular_pago_con_motivo_sube_el_saldo_y_queda_auditado` + paso 3 | ☐ |
| HU04 | Pago parcial baja el saldo y deja la factura PARCIAL | `test_pago_parcial_actualiza_saldo_y_estado` + paso 3 | ☐ |
| HU04 | Pagos hasta el total → PAGADA; el sobrepago sin confirmar se rechaza | `test_varios_pagos_hasta_el_total_pagada`, `test_pago_mayor_al_saldo_409` + paso 3 | ☐ |
| HU04 | Importe, medio y fecha validados (sin fechas futuras; anticipos permitidos) | `test_importe_invalido_422`, `test_medio_de_pago_invalido_422`, `test_fechas_de_pago` | ☐ |
| HU04 | Un reintento con la misma `Idempotency-Key` no duplica el pago | `test_reintento_con_la_misma_clave_no_duplica`, `test_doble_envio_simultaneo_con_la_misma_clave` + paso 3 | ☐ |
| HU09 | Solo el administrador anula, con motivo; el saldo se recupera | `test_operador_no_puede_anular_pago`, `test_anular_exige_motivo`, `test_admin_anula_pago_y_se_recupera_el_saldo` + paso 3 | ☐ |
| Saldo a favor | Sobrepago confirmado deja el excedente como crédito | `test_sobrepago_confirmado_deja_saldo_a_favor` + paso 3 | ☐ |
| Saldo a favor | Cobro a cuenta sin factura | `test_cobro_a_cuenta`, `test_cobro_a_cuenta_validaciones` + paso 3 | ☐ |
| Saldo a favor | Imputación manual, sin superar el disponible ni el saldo | `test_imputar_saldo_a_favor_a_otra_factura`, `test_imputar_mas_que_el_disponible_409` + paso 3 | ☐ |
| Saldo a favor | No se anula un crédito ya imputado | `test_anular_pago_con_excedente_ya_usado_se_bloquea`, `test_anular_cobro_a_cuenta` + paso 3 | ☐ |
| HU04 | Dos cobros simultáneos no superan el importe (`FOR UPDATE`) | `test_dos_pagos_simultaneos_no_superan_el_importe` | ☐ |
| §16 | Dos imputaciones simultáneas no gastan dos veces el mismo crédito | `test_dos_imputaciones_simultaneas_no_gastan_dos_veces_el_credito` | ☐ |
| HU09 | Registro y anulación quedan auditados | `test_registro_queda_auditado`, `test_admin_anula_pago_y_se_recupera_el_saldo` | ☐ |
