; Inno Setup script. Built by packaging/build.py:
;   ISCC /DAppVersion=0.1.0 /DSourceDir=dist\YouTubeDownload /DOutputDir=dist packaging\installer.iss
#ifndef IconFile
  #define IconFile "icon.ico"
#endif
#ifndef WebView2Setup
  #define WebView2Setup "MicrosoftEdgeWebview2Setup.exe"
#endif
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
; Windows 10 and 11, 64-bit (Python 3.14 itself requires Windows 10+).
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\YouTubeDownload.exe

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#WebView2Setup}"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: not IsWebView2Installed

[Icons]
Name: "{group}\YouTube Download"; Filename: "{app}\YouTubeDownload.exe"
Name: "{group}\{cm:UninstallProgram,YouTube Download}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\YouTube Download"; Filename: "{app}\YouTubeDownload.exe"; Tasks: desktopicon

[Run]
; Windows 11 ships WebView2; some Windows 10 installs don't. Install it only when missing.
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Instalando Microsoft Edge WebView2..."; Flags: waituntilterminated; Check: not IsWebView2Installed
Filename: "{app}\YouTubeDownload.exe"; Description: "{cm:LaunchProgram,YouTube Download}"; Flags: nowait postinstall skipifsilent

[Code]
const
  WebView2Key = '\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function HasVersion(RootKey: Integer; SubKey: String): Boolean;
var
  Pv: String;
begin
  Result := RegQueryStringValue(RootKey, SubKey, 'pv', Pv) and (Pv <> '') and (Pv <> '0.0.0.0');
end;

function IsWebView2Installed: Boolean;
begin
  Result := HasVersion(HKLM, 'SOFTWARE\WOW6432Node' + WebView2Key) or HasVersion(HKCU, 'Software' + WebView2Key);
end;
