<#
.SYNOPSIS
  Tareas de desarrollo de CashFlow Manager (Windows / PowerShell).

.EXAMPLE
  .\scripts\dev.ps1 setup      # crea .venv, instala dependencias y copia .env
  .\scripts\dev.ps1 up         # levanta db + api + dashboard en Docker
  .\scripts\dev.ps1 check      # verifica que todo responda
  .\scripts\dev.ps1 test       # corre los tests
  .\scripts\dev.ps1 create-admin admin@miempresa.com.ar "Nombre Apellido"
  .\scripts\dev.ps1 help       # lista de comandos
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("help", "setup", "up", "down", "reset-db", "logs", "ps", "db",
                 "migrate", "api", "dashboard", "desktop", "test", "lint",
                 "format", "check", "create-admin", "revision", "build-desktop",
                 "seed-demo", "seed-perf", "bench", "backup", "backup-verify", "demo-link")]
    [string]$Task = "help",

    [Parameter(Position = 1)]
    [string]$Arg = "",

    [Parameter(Position = 2)]
    [string]$Arg2 = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Py = Join-Path $Venv "Scripts\python.exe"
Set-Location $Root

function Write-Step([string]$msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Fail([string]$msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red }

function Invoke-Native {
    # Ejecuta un comando externo y corta si devuelve error.
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Fallo: $Exe $($Arguments -join ' ') (codigo $LASTEXITCODE)" }
}

function Assert-Venv {
    if (-not (Test-Path $Py)) { throw "No existe .venv. Ejecuta primero: .\scripts\dev.ps1 setup" }
}

function Assert-EnvFile {
    if (-not (Test-Path (Join-Path $Root ".env"))) {
        throw "Falta .env. Ejecuta: Copy-Item .env.example .env  (o .\scripts\dev.ps1 setup)"
    }
}

switch ($Task) {
    "help" {
        Get-Help $PSCommandPath -Detailed | Out-Host
        Write-Host "Comandos: setup, up, down, reset-db, logs [servicio], ps, db, migrate,"
        Write-Host "          api, dashboard, desktop, test, lint, format, check,"
        Write-Host "          create-admin <email> <nombre>, revision <mensaje>, build-desktop,"
        Write-Host "          seed-demo [reset], seed-perf [reset], bench <email>,"
        Write-Host "          backup, backup-verify <archivo.dump>, demo-link"
    }

    "setup" {
        Write-Step "Verificando Python 3.12"
        & py -3.12 --version
        if ($LASTEXITCODE -ne 0) { throw "Python 3.12 no encontrado. Instalalo desde python.org (marcar 'py launcher')." }

        if (-not (Test-Path $Py)) {
            Write-Step "Creando entorno virtual .venv"
            Invoke-Native "py" @("-3.12", "-m", "venv", $Venv)
        }
        Write-Step "Instalando dependencias (backend + dashboard + escritorio)"
        Invoke-Native $Py @("-m", "pip", "install", "--upgrade", "pip")
        Invoke-Native $Py @("-m", "pip", "install",
            "-r", "backend\requirements-dev.txt",
            "-r", "dashboard\requirements.txt",
            "-r", "desktop\requirements.txt")

        if (-not (Test-Path ".env")) {
            Copy-Item ".env.example" ".env"
            Write-Ok ".env creado desde .env.example (edita POSTGRES_PASSWORD y SECRET_KEY)"
        } else {
            Write-Ok ".env ya existe; no se modifica"
        }
        Write-Ok "Setup terminado. Activa el venv con: .\.venv\Scripts\Activate.ps1"
    }

    "up" {
        Assert-EnvFile
        Write-Step "Levantando db + api + dashboard"
        Invoke-Native "docker" @("compose", "up", "-d", "--build")
        Invoke-Native "docker" @("compose", "ps")
        Write-Host "API:       http://localhost:8000/docs"
        Write-Host "Dashboard: http://localhost:8501"
    }

    "down"  { Invoke-Native "docker" @("compose", "down") }

    "reset-db" {
        $answer = Read-Host "Esto BORRA todos los datos locales de PostgreSQL. Escribi 'si' para continuar"
        if ($answer -eq "si") {
            Invoke-Native "docker" @("compose", "down", "-v")
            Write-Ok "Volumen de datos eliminado"
        } else { Write-Host "Cancelado." }
    }

    "logs" {
        $logArgs = @("compose", "logs", "-f", "--tail", "100")
        if ($Arg) { $logArgs += $Arg }
        & docker @logArgs
    }

    "ps" { Invoke-Native "docker" @("compose", "ps") }

    "db" {
        Assert-EnvFile
        Write-Step "Levantando solo PostgreSQL (127.0.0.1:5433)"
        Invoke-Native "docker" @("compose", "up", "-d", "db")
    }

    "migrate" {
        Assert-Venv
        Push-Location backend
        try { Invoke-Native $Py @("-m", "alembic", "upgrade", "head") } finally { Pop-Location }
    }

    "create-admin" {
        Assert-Venv
        if (-not $Arg -or -not $Arg2) { throw 'Uso: .\scripts\dev.ps1 create-admin <email> "<nombre>"' }
        Push-Location backend
        try { Invoke-Native $Py @("-m", "app.cli", "create-admin", "--email", $Arg, "--name", $Arg2) } finally { Pop-Location }
    }

    "revision" {
        # Genera una migracion nueva comparando modelos vs base (revisar SIEMPRE el archivo).
        Assert-Venv
        if (-not $Arg) { throw 'Uso: .\scripts\dev.ps1 revision "descripcion del cambio"' }
        Push-Location backend
        try { Invoke-Native $Py @("-m", "alembic", "revision", "--autogenerate", "-m", $Arg) } finally { Pop-Location }
    }

    "seed-demo" {
        # Dataset de demostracion reconciliado (docs/runbook/dataset-demo.md)
        Assert-Venv
        $seedArgs = @("-m", "app.cli", "seed-demo")
        if ($Arg -eq "reset") { $seedArgs += "--reset" }
        Push-Location backend
        try { Invoke-Native $Py $seedArgs } finally { Pop-Location }
    }

    "seed-perf" {
        # 1.000 clientes, 20.000 facturas y 50.000 pagos (prueba de rendimiento)
        Assert-Venv
        $seedArgs = @("-m", "app.cli", "seed-perf")
        if ($Arg -eq "reset") { $seedArgs += "--reset" }
        Push-Location backend
        try { Invoke-Native $Py $seedArgs } finally { Pop-Location }
    }

    "bench" {
        # Mide tiempos de la API levantada (objetivo < 3 s). Uso: bench <email>
        Assert-Venv
        if (-not $Arg) { throw 'Uso: .\scripts\dev.ps1 bench <email-admin>' }
        Invoke-Native $Py @("scripts\seed\bench_metrics.py", "--email", $Arg)
    }

    "demo-link" {
        # Link HTTPS temporal al dashboard para que un cliente pruebe la demo (Cloudflare
        # Tunnel rapido, sin cuenta). Solo con datos demo y un usuario demo; Ctrl+C lo cierra.
        $cf = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
        if (-not $cf) { $cf = "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe" }
        if (-not (Test-Path $cf)) { throw "Falta cloudflared: winget install Cloudflare.cloudflared" }
        Write-Step "Busca la linea https://....trycloudflare.com y mandasela al cliente (Ctrl+C para cerrar)"
        & $cf tunnel --no-autoupdate --url "http://localhost:8501"
    }

    "backup" {
        # Backup de la base que corre en Docker -> backups\cashflow_<base>_<fecha>.dump
        Assert-Venv
        Invoke-Native $Py @("scripts\backup\backup.py", "backup", "--keep", "30")
    }

    "backup-verify" {
        # Restaura el backup en una base temporal y compara con la actual (prueba de restore)
        Assert-Venv
        if (-not $Arg) {
            $last = Get-ChildItem "backups\*.dump" -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime | Select-Object -Last 1
            if (-not $last) { throw "No hay backups. Ejecuta primero: .\scripts\dev.ps1 backup" }
            $Arg = $last.FullName
        }
        Invoke-Native $Py @("scripts\backup\backup.py", "verify", $Arg)
    }

    "api" {
        Assert-Venv
        Write-Step "API local en http://localhost:8000 (Ctrl+C para cortar)"
        Push-Location backend
        try { & $Py -m uvicorn app.main:app --reload --port 8000 } finally { Pop-Location }
    }

    "dashboard" {
        Assert-Venv
        & $Py -m streamlit run dashboard\app.py
    }

    "build-desktop" {
        # Genera dist\CashFlowManager\CashFlowManager.exe (+ zip e instalador si hay Inno Setup)
        & (Join-Path $PSScriptRoot "build\build-desktop.ps1")
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }

    "desktop" {
        Assert-Venv
        & $Py -m desktop.app.main
    }

    "test" {
        Assert-Venv
        Invoke-Native $Py @("-m", "pytest")
    }

    "lint" {
        Assert-Venv
        Invoke-Native $Py @("-m", "ruff", "check", ".")
        Invoke-Native $Py @("-m", "ruff", "format", "--check", ".")
        Write-Ok "Lint sin errores"
    }

    "format" {
        Assert-Venv
        Invoke-Native $Py @("-m", "ruff", "check", "--fix", ".")
        Invoke-Native $Py @("-m", "ruff", "format", ".")
    }

    "check" {
        $failed = $false
        try {
            $h = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health" -TimeoutSec 5
            Write-Ok "API responde: status=$($h.status) database=$($h.database) version=$($h.version)"
        } catch {
            Write-Fail "API no responde en http://localhost:8000/api/v1/health"
            $failed = $true
        }
        try {
            $d = Invoke-WebRequest -Uri "http://localhost:8501/_stcore/health" -UseBasicParsing -TimeoutSec 5
            Write-Ok "Dashboard responde (HTTP $($d.StatusCode))"
        } catch {
            Write-Fail "Dashboard no responde en http://localhost:8501"
            $failed = $true
        }
        if ($failed) { exit 1 }
    }
}
