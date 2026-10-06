#ifndef SourceRoot
  #define SourceRoot "..\.."
#endif
#ifndef AppVersion
  #define AppVersion "0.5.3"
#endif

[Setup]
AppId={{A4A5DE08-8644-4D67-B03E-271515180F7D}
AppName=Manage Your Library
AppVersion={#AppVersion}
AppPublisher=Manage Your Library
DefaultDirName={autopf}\Manage Your Library
DefaultGroupName=Manage Your Library
OutputDir={#SourceRoot}\dist\installer
OutputBaseFilename=ManageYourLibrary-{#AppVersion}-Setup-x64
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
SetupIconFile={#SourceRoot}\app_icon.ico
UninstallDisplayIcon={app}\ManageYourLibrary.exe
WizardStyle=modern

[Files]
Source: "{#SourceRoot}\dist\windows\ManageYourLibrary\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Manage Your Library"; Filename: "{app}\ManageYourLibrary.exe"
Name: "{autodesktop}\Manage Your Library"; Filename: "{app}\ManageYourLibrary.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Run]
Filename: "{app}\ManageYourLibrary.exe"; Description: "Abrir Manage Your Library"; Flags: nowait postinstall skipifsilent
