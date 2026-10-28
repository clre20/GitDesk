; Inno Setup script - produces GitDesk-Setup-<version>.exe for Windows 10/11 (x64).
; Build: run packaging\windows\build_windows.ps1 (it calls ISCC with this file).

#define AppName "GitDesk"
#ifndef AppVersion
  #define AppVersion "1.0.4"
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
CloseApplications=yes
RestartApplications=no
MinVersion=10.0

; Ask for the installer language first (pre-selects Traditional Chinese on Chinese Windows)
ShowLanguageDialog=yes
LanguageDetectionMethod=uilanguage

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
; bundled so the build does not depend on the Inno Setup version installed
Name: "chinesetraditional"; MessagesFile: "ChineseTraditional.isl"

[CustomMessages]
english.ContextMenu=Add "Open with GitDesk" to the folder right-click menu
chinesetraditional.ContextMenu=在資料夾右鍵選單加入「Open with GitDesk」
english.GitMissing=Git was not found. Please install Git for Windows: https://git-scm.com/download/win
chinesetraditional.GitMissing=找不到 Git。請安裝 Git for Windows：https://git-scm.com/download/win

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "contextmenu"; Description: "{cm:ContextMenu}"; GroupDescription: "{cm:AdditionalIcons}"

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

; Start GitDesk in the language chosen here (only if the user hasn't picked one in the app)
Root: HKCU; Subkey: "Software\GitDesk\GitDesk\ui"; ValueType: string; ValueName: "language"; ValueData: "zh_TW"; Languages: chinesetraditional; Flags: createvalueifdoesntexist
Root: HKCU; Subkey: "Software\GitDesk\GitDesk\ui"; ValueType: string; ValueName: "language"; ValueData: "en"; Languages: english; Flags: createvalueifdoesntexist

[Run]
Filename: "{app}\GitDesk.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; after an in-app (silent) update, reopen GitDesk automatically
Filename: "{app}\GitDesk.exe"; Flags: nowait runasoriginaluser; Check: WizardSilent

[Code]
function GitInstalled(): Boolean;
var ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/C git --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and (not GitInstalled()) then
    MsgBox(CustomMessage('GitMissing'),
           mbInformation, MB_OK);
end;
