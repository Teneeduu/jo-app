; jo-app 安装程序（Inno Setup 7）。
; 由 scripts\build.ps1 调用：ISCC /DAppVersion=x.y.z packaging\installer.iss
; 输入是 PyInstaller 打出来的 build\dist\jo-app\，输出 dist\jo-app-setup.exe。
;
; 默认装到 %LOCALAPPDATA%\Programs\jo-app，不需要管理员权限。
; 用户数据在 %APPDATA%\jo-app，卸载时不动 —— 重装、升级任务都还在。

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppExe "jo-app.exe"

[Setup]
; AppId 定了就别改 —— 升级安装靠它认出「这是同一个程序」
AppId={{8C3F5E7A-4B2D-4E61-9A7C-2D1F0B6E9A31}
AppName=jo-app
AppVersion={#AppVersion}
AppVerName=jo-app {#AppVersion}
AppPublisher=Teneeduu
AppPublisherURL=https://github.com/Teneeduu/jo-app
AppSupportURL=https://github.com/Teneeduu/jo-app/issues
AppUpdatesURL=https://github.com/Teneeduu/jo-app/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\jo-app
DefaultGroupName=jo-app
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=jo-app-setup
SetupIconFile=..\joapp\resources\jo-app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName=jo-app
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; jo-app 开着的时候 exe 被占用，覆盖不了。这个名字和 joapp/ui/app.py 的
; INSTALLER_MUTEX 一致：检测到就请用户先退出（托盘右键 →「退出」）。
AppMutex=jo-app-running

[Languages]
Name: "chs"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "在桌面创建快捷方式"; GroupDescription: "附加选项："
Name: "autostart"; Description: "开机自动启动（打开电脑就看到任务，休息提醒自动开始）"; GroupDescription: "附加选项："

[InstallDelete]
; 升级时先清掉旧版的运行库，免得新旧两版的 Qt 文件混在一起
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\build\dist\jo-app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\jo-app"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\jo-app"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "jo-app"; ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "现在打开 jo-app"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
