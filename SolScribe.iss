#define MyAppName "SolScribe"
#define MyAppVersion "0.2.2"
#define MyAppExeName "SolScribe.exe"

[Setup]
AppId={{B9B27792-080D-4B54-A0B1-6C5DBB5DE071}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=SolScribe
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=SolScribe-Setup-0.2.2
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\solscribe.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "dist\SolScribe\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\SolScribe"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\SolScribe"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch SolScribe"; Flags: nowait postinstall skipifsilent
