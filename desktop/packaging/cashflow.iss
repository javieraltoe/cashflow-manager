; Inno Setup 6 · instalador de CashFlow Manager (preliminar, sin firma digital).
; Lo compila .\scripts\build\build-desktop.ps1 si Inno Setup está instalado:
;   ISCC.exe /DAppVersion=0.3.0 desktop\packaging\cashflow.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6B3C2E7A-4F1D-4C8B-9A2E-CF1A5D7B3E90}
AppName=CashFlow Manager
AppVersion={#AppVersion}
AppPublisher=CashFlow Manager
DefaultDirName={autopf}\CashFlow Manager
DefaultGroupName=CashFlow Manager
; Instalación por usuario: no pide permisos de administrador.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=CashFlowManager-Setup-{#AppVersion}
SetupIconFile=cashflow.ico
UninstallDisplayIcon={app}\CashFlowManager.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
MinVersion=10.0

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\..\dist\CashFlowManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CashFlow Manager"; Filename: "{app}\CashFlowManager.exe"
Name: "{group}\Desinstalar CashFlow Manager"; Filename: "{uninstallexe}"
Name: "{autodesktop}\CashFlow Manager"; Filename: "{app}\CashFlowManager.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CashFlowManager.exe"; Description: "Abrir CashFlow Manager"; Flags: nowait postinstall skipifsilent
