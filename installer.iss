#define AppName "Orvilo"
#define AppVersion "1.1.0"
[Setup]
AppId={{47B21846-BD41-4126-A371-F3492F997018}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Orvilo
AppPublisherURL=https://github.com/aadiichau/orvilo
AppSupportURL=https://github.com/aadiichau/orvilo/issues
AppUpdatesURL=https://github.com/aadiichau/orvilo/releases
DefaultDirName={localappdata}\Programs\Orvilo
DefaultGroupName=Orvilo
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=dist
OutputBaseFilename=Orvilo-Setup-{#AppVersion}
SetupIconFile=assets\logo.ico
UninstallDisplayIcon={app}\Orvilo.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=LICENSES\GPL-3.0.txt
CloseApplications=yes
RestartApplications=no
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
[Files]
Source: "dist\Orvilo.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "LICENSES\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "DEPENDENCY_SOURCES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{autoprograms}\Orvilo"; Filename: "{app}\Orvilo.exe"
Name: "{autodesktop}\Orvilo"; Filename: "{app}\Orvilo.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\Orvilo.exe"; Description: "Open Orvilo"; Flags: nowait postinstall skipifsilent
