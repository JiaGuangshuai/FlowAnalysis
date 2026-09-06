[Setup]
AppId=org.flowanalysis.desktop
AppName=FlowAnalysis
AppVersion=0.1.0
AppPublisher=FlowAnalysis contributors
DefaultDirName={localappdata}\Programs\FlowAnalysis
DefaultGroupName=FlowAnalysis
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=FlowAnalysis-0.1.0-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\FlowAnalysis.exe
LicenseFile=..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\FlowAnalysis\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\FlowAnalysis"; Filename: "{app}\FlowAnalysis.exe"
Name: "{userdesktop}\FlowAnalysis"; Filename: "{app}\FlowAnalysis.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FlowAnalysis.exe"; Description: "Launch FlowAnalysis"; Flags: nowait postinstall skipifsilent
