#define AppName "Audio Capture Studio"
#define AppVersion "1.0.0"
#define AppPublisher "Audio Capture Studio"
#define AppExeName "AudioCaptureStudio.exe"

[Setup]
AppId={{A236A054-0FA4-42FC-9BD7-2F8ACDE28E2B}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Audio Capture Studio
DefaultGroupName={#AppName}
OutputDir=..\dist
OutputBaseFilename=AudioCaptureStudio-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#AppExeName}

[Files]
Source: "..\dist\AudioCaptureStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Audio Capture Studio"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\Audio Capture Studio"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch Audio Capture Studio"; Flags: postinstall nowait skipifsilent
