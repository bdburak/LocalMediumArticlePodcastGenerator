; LocalMediumPodcast Inno Setup installer script
; Build: iscc /DAPP_VERSION=0.1.0 installer\installer.iss

#ifndef APP_VERSION
  #define APP_VERSION "0.0.0"
#endif

[Setup]
AppName=Local Medium Article Podcast Generator
AppVersion={#APP_VERSION}
AppPublisher=LocalMediumPodcast
DefaultDirName={autopf}\LocalMediumPodcast
DefaultGroupName=Local Medium Podcast
OutputDir=Output
OutputBaseFilename=LocalMediumPodcast-Setup-v{#APP_VERSION}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
DisableProgramGroupPage=yes
LicenseFile=LICENSE
UninstallDisplayIcon={app}\LocalMediumPodcast.ico
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "staging\app\*"; DestDir: "{app}\app"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "staging\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "staging\uv\uv.exe"; DestDir: "{app}\uv"; Flags: ignoreversion
Source: "staging\scripts\first_run.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "staging\scripts\launch.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "staging\LocalMediumPodcast.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Local Medium Podcast"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\first_run.ps1"""; IconFilename: "{app}\LocalMediumPodcast.ico"
Name: "{autodesktop}\Local Medium Podcast"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\first_run.ps1"""; IconFilename: "{app}\LocalMediumPodcast.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"

[Run]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\first_run.ps1"""; Description: "Launch first-run wizard"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; No_TRANSFORM needed — uninstall just removes files. Cached models/venv left intact by default.

[UninstallDelete]
Type: filesandordirs; Name: "{app}"