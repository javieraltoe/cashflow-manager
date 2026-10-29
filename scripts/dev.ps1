<#
.SYNOPSIS
  Tareas de desarrollo de CashFlow Manager (Windows / PowerShell).

.EXAMPLE
  .\scripts\dev.ps1 setup      # crea .venv, instala dependencias y copia .env
  .\scripts\dev.ps1 up         # levanta db + api + dashboard en Docker
  .\scripts\dev.ps1 check      # verifica que todo responda
  .\scripts\dev.ps1 test       # corre los tests
  .\scripts\dev.ps1 help       # lista de comandos
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("help", "setup", "up", "down", "reset-db", "logs", "ps", "db",
                 "migrate", "api", "dashboard", "desktop", "test", "lint",
                 "format", "check")]
    [string]$Task = "help",

    [Parameter(Position = 1)]
    [string]$Arg = ""
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
        Write-Host "          api, dashboard, desktop, test, lint, format, check"
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
