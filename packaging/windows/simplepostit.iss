; Instalador de Windows (Inno Setup 6):  iscc /DVersion=1.0.0 packaging\windows\simplepostit.iss
; Instala para el usuario actual (sin permisos de administrador) desde dist\SimplePost-It.
#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{6F0D6C1E-6A5B-4B7E-9D3C-5A1F2E8B9C47}
AppName=SimplePost-It
AppVersion={#Version}
AppPublisher=Frank
AppPublisherURL=https://github.com/FrankMncrf/SimplePost-It
DefaultDirName={localappdata}\Programs\SimplePost-It
DefaultGroupName=SimplePost-It
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=SimplePost-It-{#Version}-windows-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\SimplePost-It.exe
LicenseFile=..\..\LICENSE

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\..\dist\SimplePost-It\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\SimplePost-It"; Filename: "{app}\SimplePost-It.exe"

[Registry]
; el inicio con la sesión lo crea la app (Ajustes); al desinstalar se quita
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "SimplePost-It"; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\SimplePost-It.exe"; Description: "{cm:LaunchProgram,SimplePost-It}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\SimplePost-It.exe"; Parameters: "--quit"; Flags: runhidden; RunOnceId: "QuitApp"
