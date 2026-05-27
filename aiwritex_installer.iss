[Setup]
; 新 AppId：与旧版 AIWriteX 安装记录脱钩，默认目录才会是 XBoom
AppId={{B8E4F2A1-6C3D-4F9E-A1B2-7D8E9F0C4A5B}
AppName=小爆来咯
AppVersion=1.0.2
AppPublisher=小爆来咯
DefaultDirName={autopf}\XBoom
DefaultGroupName=小爆来咯
; 安装向导中可浏览修改目录；默认 {autopf}\XBoom，不沿用旧版 AIWriteX 路径
DisableDirPage=no
UsePreviousAppDir=no
DisableProgramGroupPage=yes
OutputDir=dist\installer
OutputBaseFilename=XBoom-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
; 静默更新时自动结束正在运行的 XBoom，并在安装完成后重新启动
CloseApplications=force
RestartApplications=yes
UninstallDisplayIcon={app}\XBoom.exe
SetupIconFile=src\ai_write_x\assets\branding\app_icon.ico

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:";

[Files]
Source: "dist\XBoom\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\小爆来咯"; Filename: "{app}\XBoom.exe"
Name: "{autodesktop}\小爆来咯"; Filename: "{app}\XBoom.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\XBoom.exe"; Description: "启动 小爆来咯"; Flags: nowait postinstall skipifsilent
