[Setup]
AppId={{F9DE6B5D-57BD-4E43-B8AE-AFD2D17FE682}
AppName=AIWriteX
AppVersion=23.0.9
AppPublisher=AIWriteX
DefaultDirName={autopf}\AIWriteX
DefaultGroupName=AIWriteX
DisableProgramGroupPage=yes
OutputDir=dist\installer
OutputBaseFilename=AIWriteX-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\AIWriteX.exe
SetupIconFile=src\ai_write_x\assets\branding\app_icon.ico

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:";

[Files]
Source: "dist\AIWriteX\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\AIWriteX"; Filename: "{app}\AIWriteX.exe"
Name: "{autodesktop}\AIWriteX"; Filename: "{app}\AIWriteX.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AIWriteX.exe"; Description: "启动 AIWriteX"; Flags: nowait postinstall skipifsilent
