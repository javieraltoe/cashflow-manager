<#
.SYNOPSIS
  Genera el ejecutable de Windows de CashFlow Manager (y el instalador si hay Inno Setup).

.DESCRIPTION
  1. Corre los tests del escritorio (salvo -SkipTests).
  2. PyInstaller -> dist\CashFlowManager\CashFlowManager.exe (carpeta ejecutable).
  3. Comprime la carpeta -> dist\CashFlowManager-<version>-win64.zip
  4. Si Inno Setup 6.3+ esta instalado -> dist\CashFlowManager-Setup-<version>.exe

.EXAMPLE
  .\scripts\build\build-desktop.ps1
  .\scripts\build\build-desktop.ps1 -SkipTests
#>
param([switch]$SkipTests)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Py = Join-Path $Root ".venv\Scripts\python.exe"
Set-Location $Root

function Write-Step([string]$msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "[OK]    $msg" -ForegroundColor Green }

if (-not (Test-Path $Py)) { throw "No existe .venv. Ejecuta primero: .\scripts\dev.ps1 setup" }

# Version desde desktop/app/__init__.py
$init = Get-Content "desktop\app\__init__.py" -Raw
if ($init -notmatch '__version__\s*=\s*"(\d+)\.(\d+)\.(\d+)"') { throw "No se encontro __version__" }
$Version = "$($Matches[1]).$($Matches[2]).$($Matches[3])"
$VerTuple = "($($Matches[1]), $($Matches[2]), $($Matches[3]), 0)"
Write-Step "CashFlow Manager $Version"

if (-not $SkipTests) {
    Write-Step "Tests del escritorio"
    & $Py -m pytest desktop\tests -q
    if ($LASTEXITCODE -ne 0) { throw "Hay tests que fallan: no se genera el ejecutable." }
}

# Metadatos del .exe con la version actual
$versionFile = "desktop\packaging\version_info.txt"
$content = Get-Content $versionFile -Raw
$content = $content -replace 'filevers=\([^)]*\)', "filevers=$VerTuple"
$content = $content -replace 'prodvers=\([^)]*\)', "prodvers=$VerTuple"
$content = $content -replace "StringStruct\('FileVersion', '[^']*'\)", "StringStruct('FileVersion', '$Version')"
$content = $content -replace "StringStruct\('ProductVersion', '[^']*'\)", "StringStruct('ProductVersion', '$Version')"
# Sin BOM: PyInstaller evalua este archivo como Python.
[System.IO.File]::WriteAllText((Join-Path $Root $versionFile), $content)

Write-Step "PyInstaller (puede tardar unos minutos)"
if (Test-Path "dist\CashFlowManager") { Remove-Item "dist\CashFlowManager" -Recurse -Force }
& $Py -m PyInstaller "desktop\packaging\cashflow.spec" --noconfirm --clean --distpath dist --workpath "build\pyinstaller"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fallo." }
$exe = "dist\CashFlowManager\CashFlowManager.exe"
if (-not (Test-Path $exe)) { throw "No se genero $exe" }
Write-Ok "Ejecutable: $exe"

Write-Step "Comprimiendo carpeta portable"
$zip = "dist\CashFlowManager-$Version-win64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
# El antivirus suele revisar los archivos recien generados y los bloquea unos segundos.
for ($try = 1; ; $try++) {
    try { Compress-Archive -Path "dist\CashFlowManager" -DestinationPath $zip -Force; break }
    catch {
        if ($try -ge 5) { throw }
        Write-Host "  Archivo en uso (antivirus?), reintento $try de 4..." -ForegroundColor Yellow
        Start-Sleep -Seconds 5
    }
}
Write-Ok "Portable: $zip"

$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

if ($iscc) {
    Write-Step "Instalador (Inno Setup)"
    & $iscc "/DAppVersion=$Version" "desktop\packaging\cashflow.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup fallo." }
    Write-Ok "Instalador: dist\CashFlowManager-Setup-$Version.exe"
} else {
    Write-Host "Inno Setup no esta instalado: se omite el instalador." -ForegroundColor Yellow
    Write-Host "  Instalalo con: winget install JRSoftware.InnoSetup  y volve a ejecutar este script."
}
