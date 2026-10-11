; Inno Setup script. Built by packaging/build.py:
;   ISCC /DAppVersion=0.1.0 /DSourceDir=dist\Pista /DOutputDir=dist packaging\installer.iss
#ifndef IconFile
  #define IconFile "icon.ico"
#endif
#ifndef WebView2Setup
  #define WebView2Setup "MicrosoftEdgeWebview2Setup.exe"
#endif
#ifndef LicenseFile
  #define LicenseFile "..\LICENSE"
#endif
#ifndef NoticesFile
  #define NoticesFile "..\.github\THIRD_PARTY_NOTICES.md"
#endif
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8F6C2B7E-3D41-4C5A-9E2F-6B1D7A0C5E93}
AppName=Pista
AppVerName=Pista {#AppVersion}
AppVersion={#AppVersion}
AppPublisher=JySa65
DefaultDirName={autopf}\Pista
; Same AppId as <= 0.2.x («YouTube Download»): installing over it upgrades it (one entry in Apps).
; Don't reuse the old folder name; the old files are removed in [InstallDelete].
UsePreviousAppDir=no
UsePreviousGroup=no
DefaultGroupName=Pista
DisableProgramGroupPage=yes
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutputDir}
OutputBaseFilename=Pista-Setup-{#AppVersion}
LicenseFile={#LicenseFile}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Windows 10 and 11, 64-bit (Python 3.14 itself requires Windows 10+).
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\Pista.exe

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Leftovers of the pre-rename app (<= 0.2.x), installed per-machine or per-user. Its uninstall entry is
; replaced by this one because the AppId is the same.
Type: filesandordirs; Name: "{commonpf64}\YouTubeDownload"
Type: filesandordirs; Name: "{userpf}\YouTubeDownload"
Type: filesandordirs; Name: "{commonprograms}\YouTube Download"
Type: filesandordirs; Name: "{userprograms}\YouTube Download"
Type: files; Name: "{commondesktop}\YouTube Download.lnk"
Type: files; Name: "{userdesktop}\YouTube Download.lnk"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#LicenseFile}"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "{#NoticesFile}"; DestDir: "{app}"; DestName: "THIRD_PARTY_NOTICES.md"; Flags: ignoreversion
Source: "{#WebView2Setup}"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: not IsWebView2Installed

[Icons]
Name: "{group}\Pista"; Filename: "{app}\Pista.exe"
Name: "{group}\{cm:UninstallProgram,Pista}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Pista"; Filename: "{app}\Pista.exe"; Tasks: desktopicon

[Run]
; Windows 11 ships WebView2; some Windows 10 installs don't. Install it only when missing.
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Instalando Microsoft Edge WebView2..."; Flags: waituntilterminated; Check: not IsWebView2Installed
Filename: "{app}\Pista.exe"; Description: "{cm:LaunchProgram,Pista}"; Flags: nowait postinstall skipifsilent

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
