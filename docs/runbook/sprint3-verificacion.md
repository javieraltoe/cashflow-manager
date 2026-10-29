# Sprint 3 · Verificación de la aplicación de escritorio

Ejecutar en PowerShell desde la raíz del repo, con Docker Desktop abierto.

## 1. Dependencias y tests

```powershell
.\scripts\dev.ps1 setup          # suma tzdata al escritorio
.\scripts\dev.ps1 up
.\scripts\dev.ps1 lint           # All checks passed!
.\scripts\dev.ps1 test           # backend + escritorio, incluidos los de interfaz
```

Resultado esperado con Docker arriba: **`259 passed`**, 0 saltados. Los tests de
interfaz (`desktop/tests/test_ui_smoke.py`) abren cada pantalla en modo invisible; si
aparecen como `skipped`, PySide6 no está instalado en el `.venv`.

## 2. Prueba manual (15 minutos)

```powershell
.\scripts\dev.ps1 desktop
```

| # | Pantalla | Qué hacer | Resultado esperado | ✔ |
|---|---|---|---|---|
| 1 | Login | Servidor `localhost:8000`, email y contraseña incorrecta | "Email o contraseña incorrectos" en rojo | ✔ |
| 2 | Login | Contraseña correcta | Abre la ventana principal con tu nombre y rol arriba | ✔ |
| 3 | Inicio | Mirar las tarjetas | Conteos de vencidas, próximos 7 días y clientes activos | ✔ |
| 4 | Clientes | Nuevo cliente "ACME SA" y después otro "acme sa" | El segundo marca el nombre en rojo: "Ya existe un cliente…" | ✔ |
| 5 | Clientes | Buscar "acm" | Aparece ACME SA | ✔ |
| 6 | Facturas | Nueva factura, importe `125.000,50` | En la lista: $ 125.000,50, estado Pendiente | ✔ |
| 7 | Facturas | Otra con el mismo número para el mismo cliente | Número resaltado: "Ya existe una factura con ese número…" | ✔ |
| 8 | Facturas | Registrar pago de `25.000,25` | Saldo $ 100.000,25, estado Parcial (HU04) | ✔ |
| 9 | Facturas | Registrar pago de `200.000` | Pregunta si el excedente queda como saldo a favor; "No" deja el formulario abierto | ✔ |
| 10 | Facturas | Doble clic rápido en "Registrar pago" | Un solo pago en el detalle | ✔ |
| 11 | Facturas → Ver detalle | Seleccionar un pago → Anular, motivo "cheque rechazado" (admin) | El saldo vuelve a subir; el pago figura "Anulado: cheque rechazado" (HU09) | ✔ |
| 12 | Saldo a favor | Elegir cliente → Cobro a cuenta $ 10.000 → Imputar a factura | Disponible baja y el saldo de la factura también | ✔ |
| 13 | Configuración | Como **operador** | No aparecen "Usuarios" ni los botones "Anular" | ✔ |
| 14 | Configuración | Cambiar contraseña | Pide volver a ingresar | ✔ |
| 15 | Cualquiera | `docker compose stop api` y apretar F5 | "No se pudo conectar con el servidor…" sin cerrarse la app; `docker compose start api` | ✔ |
| 16 | Inicio | "Abrir dashboard web" | Abre http://localhost:8501 en el navegador | ✔ |

## 3. Ejecutable e instalador

```powershell
winget install JRSoftware.InnoSetup      # opcional, una sola vez (para el instalador)
.\scripts\dev.ps1 build-desktop
```

Resultado esperado en `dist\`:

| Archivo | Para qué |
|---|---|
| `CashFlowManager\CashFlowManager.exe` | Ejecutable (carpeta completa) |
| `CashFlowManager-0.3.0-win64.zip` | Versión portable: descomprimir y ejecutar |
| `CashFlowManager-Setup-0.3.0.exe` | Instalador (solo si está Inno Setup) |

Probar en **otra PC sin Python** (o en una cuenta de Windows nueva):
1. Instalar con `CashFlowManager-Setup-0.3.0.exe` (no pide permisos de administrador).
2. Abrir "CashFlow Manager" desde el menú Inicio.
3. En el login, poner la dirección del servidor. En la misma PC: `localhost:8000`.
   Desde otra PC de la red local: `http://IP-DE-TU-PC:8000`, para lo cual hay que cambiar
   **temporalmente** en `docker-compose.yml` el puerto de la `api` de `127.0.0.1:` a
   `0.0.0.0:` (nunca el de la base) y permitir el puerto 8000 en el firewall de Windows.
   Volvé atrás al terminar: el acceso desde otras PCs con HTTPS se arma en el Sprint 5.
4. Windows SmartScreen puede advertir "editor desconocido" porque el ejecutable no está
   firmado todavía: "Más información" → "Ejecutar de todas formas". La firma se agrega
   en el Sprint 5.
