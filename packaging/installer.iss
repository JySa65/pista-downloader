; Inno Setup script. Built by packaging/build.py:
;   ISCC /DAppVersion=0.1.0 /DSourceDir=dist\YouTubeDownload /DOutputDir=dist packaging\installer.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8F6C2B7E-3D41-4C5A-9E2F-6B1D7A0C5E93}
AppName=YouTube Download
AppVersion={#AppVersion}
AppPublisher=JySa65
DefaultDirName={autopf}\YouTubeDownload
DefaultGroupName=YouTube Download
DisableProgramGroupPage=yes
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutputDir}
OutputBaseFilename=YouTubeDownload-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\YouTubeDownload.exe

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\YouTube Download"; Filename: "{app}\YouTubeDownload.exe"
Name: "{group}\{cm:UninstallProgram,YouTube Download}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\YouTube Download"; Filename: "{app}\YouTubeDownload.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\YouTubeDownload.exe"; Description: "{cm:LaunchProgram,YouTube Download}"; Flags: nowait postinstall skipifsilent
