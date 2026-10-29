# Sprint 1 · Verificación de criterios de aceptación

Ejecutar en PowerShell desde la raíz del repo, con Docker Desktop abierto.

## 1. Instalar dependencias nuevas y migrar

```powershell
.\scripts\dev.ps1 setup          # instala argon2-cffi, PyJWT, email-validator, tzdata
.\scripts\dev.ps1 up             # reconstruye la imagen de la API (aplica la migración 0001)
.\scripts\dev.ps1 logs api       # debe aparecer: Running upgrade  -> 0001  (Ctrl+C para salir)
```

## 2. Pruebas automáticas

```powershell
.\scripts\dev.ps1 lint           # All checks passed!
.\scripts\dev.ps1 test           # 111 passed  (con Docker arriba)
```

Sin Docker el resultado esperado es `47 passed, 64 skipped`.

## 3. Crear el primer administrador

```powershell
.\scripts\dev.ps1 create-admin admin@miempresa.com.ar "Administrador"
# Pide la contraseña dos veces (mínimo 10 caracteres)
# Esperado: Administrador creado: admin@miempresa.com.ar (id ...)
```

## 4. Prueba manual de la API (PowerShell)

```powershell
$B = "http://localhost:8000/api/v1"
$login = Invoke-RestMethod -Method Post "$B/auth/login" -ContentType "application/json" `
  -Body (@{ email = "admin@miempresa.com.ar"; password = "TU_CLAVE" } | ConvertTo-Json)
$H = @{ Authorization = "Bearer $($login.access_token)" }

Invoke-RestMethod "$B/me" -Headers $H                      # role: admin

# HU02: cliente + búsqueda
$c = Invoke-RestMethod -Method Post "$B/clients" -Headers $H -ContentType "application/json" `
  -Body (@{ name = "ACME SA"; tax_id = "30-71234567-8" } | ConvertTo-Json)
(Invoke-RestMethod "$B/clients?q=acme" -Headers $H).total  # 1

# HU03: factura con saldo
$f = Invoke-RestMethod -Method Post "$B/invoices" -Headers $H -ContentType "application/json" `
  -Body (@{ client_id = $c.id; invoice_number = "F-0001"; issue_date = "2026-10-01";
            due_date = "2026-10-20"; amount = "125000.50" } | ConvertTo-Json)
$f | Select-Object invoice_number, amount, balance, status, days_overdue
# balance 125000.50 · status VENCIDA (vence antes de hoy) · days_overdue > 0  -> HU05

# HU03: número duplicado para el mismo cliente -> 409
try {
  Invoke-RestMethod -Method Post "$B/invoices" -Headers $H -ContentType "application/json" `
    -Body (@{ client_id = $c.id; invoice_number = "F-0001"; issue_date = "2026-10-01";
              due_date = "2026-10-30"; amount = "1" } | ConvertTo-Json)
} catch { $_.ErrorDetails.Message }   # {"error":{"code":"duplicate_invoice_number",...}}

# Filtro por estado
(Invoke-RestMethod "$B/invoices?status=VENCIDA" -Headers $H).total   # 1
```

También podés probar todo desde <http://localhost:8000/docs> con el botón **Authorize**:
pegá el `access_token` (sin "Bearer").

## 5. Checklist

| HU | Criterio | Cómo se verifica | ✔ |
|---|---|---|---|
| HU01 | El admin ingresa; el operador no administra usuarios | `test_auth_api.py`, `test_users_api.py` (403) | ☐ |
| HU02 | Cliente creado y encontrado por búsqueda; nombre obligatorio | `test_clients_api.py` + paso 4 | ☐ |
| HU03 | Factura con saldo visible; número duplicado → error | `test_invoices_api.py` + paso 4 | ☐ |
| HU05 | Factura impaga vencida pasa a VENCIDA sola | `test_hu05_vence_sola_sin_intervencion` + paso 4 | ☐ |
| §5 | Saldo/estado/mora/antigüedad con Decimal | `test_invoice_rules.py` | ☐ |
| §7 | Migraciones = modelos; restricciones UNIQUE/CHECK | `test_migrations.py` | ☐ |
