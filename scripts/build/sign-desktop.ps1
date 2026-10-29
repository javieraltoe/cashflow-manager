<#
.SYNOPSIS
  Firma digitalmente el ejecutable y el instalador de CashFlow Manager (Authenticode).

.DESCRIPTION
  Requiere un certificado de firma de codigo (OV o EV) emitido por una CA reconocida
  y signtool.exe (Windows SDK). El certificado se toma de:
    - CODESIGN_PFX + CODESIGN_PASSWORD (archivo .pfx), o
    - CODESIGN_THUMBPRINT (certificado instalado en el almacen del usuario / token EV).
  Nunca guardar el .pfx ni la contrasena en el repositorio.

.EXAMPLE
  $env:CODESIGN_THUMBPRINT = "ABCDEF0123..."
  .\scripts\build\sign-desktop.ps1 dist\CashFlowManager\CashFlowManager.exe
#>
param([Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)][string[]]$Files)

$ErrorActionPreference = "Stop"
$Timestamp = "http://timestamp.digicert.com"

$signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" `
    -ErrorAction SilentlyContinue | Sort-Object FullName | Select-Object -Last 1
if (-not $signtool) {
    throw "No se encontro signtool.exe. Instala el Windows SDK: winget install Microsoft.WindowsSDK.10.0.26100"
}

$certArgs = @()
if ($env:CODESIGN_THUMBPRINT) {
    $certArgs = @("/sha1", $env:CODESIGN_THUMBPRINT)
} elseif ($env:CODESIGN_PFX) {
    if (-not (Test-Path $env:CODESIGN_PFX)) { throw "No existe $env:CODESIGN_PFX" }
    $certArgs = @("/f", $env:CODESIGN_PFX, "/p", $env:CODESIGN_PASSWORD)
} else {
    throw "Defini CODESIGN_THUMBPRINT o CODESIGN_PFX (+ CODESIGN_PASSWORD)."
}

foreach ($file in $Files) {
    if (-not (Test-Path $file)) { throw "No existe $file" }
    Write-Host "==> Firmando $file" -ForegroundColor Cyan
    & $signtool.FullName sign /fd SHA256 /td SHA256 /tr $Timestamp `
        /d "CashFlow Manager" @certArgs $file
    if ($LASTEXITCODE -ne 0) { throw "signtool fallo al firmar $file" }
    & $signtool.FullName verify /pa /q $file
    if ($LASTEXITCODE -ne 0) { throw "La firma de $file no verifica" }
    Write-Host "[OK]    Firma verificada" -ForegroundColor Green
}
