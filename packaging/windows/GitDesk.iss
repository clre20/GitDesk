; Inno Setup script - produces GitDesk-Setup-<version>.exe for Windows 10/11 (x64).
; Build: run packaging\windows\build_windows.ps1 (it calls ISCC with this file).

#define AppName "GitDesk"
#ifndef AppVersion
  #define AppVersion "1.0.1"
#endif

[Setup]
AppId={{6E7C5B8A-3C1D-4E8B-9F0A-1D2C3B4A5F60}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=GitDesk
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\GitDesk.exe
OutputDir=..\..\dist
OutputBaseFilename=GitDesk-Setup-{#AppVersion}
SetupIconFile=..\gitdesk.ico
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "contextmenu"; Description: "Add ""Open with GitDesk"" to folder right-click menu"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\GitDesk\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\GitDesk.exe"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\GitDesk.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\Directory\shell\GitDesk"; ValueType: string; ValueName: ""; ValueData: "Open with GitDesk"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Directory\shell\GitDesk"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\GitDesk.exe"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\shell\GitDesk\command"; ValueType: string; ValueName: ""; ValueData: """{app}\GitDesk.exe"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\Background\shell\GitDesk"; ValueType: string; ValueName: ""; ValueData: "Open with GitDesk"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Directory\Background\shell\GitDesk"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\GitDesk.exe"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\Background\shell\GitDesk\command"; ValueType: string; ValueName: ""; ValueData: """{app}\GitDesk.exe"" ""%V"""; Tasks: contextmenu

[Run]
Filename: "{app}\GitDesk.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function GitInstalled(): Boolean;
var ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/C git --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and (not GitInstalled()) then
    MsgBox('Git was not found. Please install Git for Windows: https://git-scm.com/download/win',
           mbInformation, MB_OK);
end;
