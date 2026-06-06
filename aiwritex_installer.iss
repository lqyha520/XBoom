[Setup]
AppId={{B8E4F2A1-6C3D-4F9E-A1B2-7D8E9F0C4A5B}}
AppName=小爆来咯
AppVersion=1.2.13
AppPublisher=小爆来咯
DefaultDirName={autopf}\小爆来咯
DefaultGroupName=小爆来咯
DisableDirPage=no
UsePreviousAppDir=no
DisableProgramGroupPage=yes
OutputDir=dist\installer
OutputBaseFilename=小爆来咯-Setup-v1.2.13
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\小爆来咯.exe
SetupIconFile=src\ai_write_x\assets\branding\app_icon.ico

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional tasks:";
Name: "installwebview2"; Description: "Install Microsoft WebView2 Runtime (required)"; GroupDescription: "Components:"; Flags: checkedonce

[Files]
Source: "dist\小爆来咯\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "installer_assets\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Tasks: installwebview2; Check: WebView2NeedsInstall

[Icons]
Name: "{group}\小爆来咯"; Filename: "{app}\小爆来咯.exe"
Name: "{autodesktop}\小爆来咯"; Filename: "{app}\小爆来咯.exe"; Tasks: desktopicon

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; WorkingDir: {tmp}; StatusMsg: "Installing Microsoft WebView2 Runtime..."; Tasks: installwebview2; Check: WebView2NeedsInstall; Flags: runhidden waituntilterminated
Filename: "{app}\小爆来咯.exe"; Description: "Launch 小爆来咯"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\logs\*"

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: string; ValueName: "AIWRITEX_DISABLE_BROWSER_FALLBACK"; ValueData: "1"; Flags: uninsdeletevalue preservestringtype
Root: HKCU; Subkey: "Environment"; ValueType: string; ValueName: "AIWRITEX_BROWSER_GUI"; ValueData: "0"; Flags: uninsdeletevalue preservestringtype

[Code]
function GetWebView2Version(): string;
var
  RegVersion: string;
begin
  Result := '';
  if RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3B927B189}', 'pv', RegVersion) then
    Result := RegVersion
  else if RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3B927B189}', 'pv', RegVersion) then
    Result := RegVersion;
end;

function WebView2NeedsInstall: Boolean;
var
  Version: string;
begin
  Version := GetWebView2Version();
  if Version = '' then begin
    Log('WebView2 not installed');
    Result := True;
  end else begin
    Log('WebView2 installed, version: ' + Version);
    Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  FlagFile: string;
  InternalDir: string;
begin
  if CurStep = ssInstall then begin
    InternalDir := ExpandConstant('{app}\_internal');
    if DirExists(InternalDir) then begin
      Log('Removing old _internal directory: ' + InternalDir);
      DelTree(InternalDir, True, True, True);
      Log('Old _internal directory removed');
    end;
  end;

  if CurStep = ssPostInstall then begin
    Log('Post-install cleanup...');

    FlagFile := ExpandConstant('{app}\logs\use_browser_gui.flag');
    if FileExists(FlagFile) then begin
      if DeleteFile(FlagFile) then
        Log('Deleted browser fallback flag')
      else
        Log('Failed to delete flag');
    end;
  end;
end;
