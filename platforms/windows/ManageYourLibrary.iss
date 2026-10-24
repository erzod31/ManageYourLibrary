#ifndef SourceRoot
  #define SourceRoot "..\.."
#endif
#ifndef AppVersion
  #define AppVersion "0.5.3"
#endif
#ifndef SourcePayload
  #define SourcePayload SourceRoot + "\dist\windows\ManageYourLibrary"
#endif
#ifndef InstallerOutput
  #define InstallerOutput SourceRoot + "\dist\installer"
#endif

[Setup]
#ifdef ValidationAppId
AppId={#ValidationAppId}
#else
AppId={{A4A5DE08-8644-4D67-B03E-271515180F7D}
#endif
AppName=Manage Your Library
AppVersion={#AppVersion}
AppPublisher=Manage Your Library
DefaultDirName={autopf}\Manage Your Library
DefaultGroupName=Manage Your Library
OutputDir={#InstallerOutput}
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
Source: "{#SourcePayload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

#ifndef ValidationAppId
[Icons]
Name: "{autoprograms}\Manage Your Library"; Filename: "{app}\ManageYourLibrary.exe"
Name: "{autodesktop}\Manage Your Library"; Filename: "{app}\ManageYourLibrary.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked
#endif

[Run]
Filename: "{app}\ManageYourLibrary.exe"; Description: "Abrir Manage Your Library"; Flags: nowait postinstall skipifsilent
