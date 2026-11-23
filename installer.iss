#define AppName "Claude Usage Tray"
#define AppExe "ClaudeUsageTray.exe"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{735F814C-0673-4713-A4D3-B08D8B0A7938}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=codezzium
AppPublisherURL=https://github.com/codezzium/claude-usage-tray
AppSupportURL=https://github.com/codezzium/claude-usage-tray/issues
DefaultDirName={autopf}\ClaudeUsageTray
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=no
ShowLanguageDialog=auto
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
OutputDir=dist
OutputBaseFilename=ClaudeUsageTraySetup
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "startup"; Description: "{cm:AutoStartProgram,{#AppName}}"; GroupDescription: "{cm:AutoStartProgramGroupDescription}"

[Files]
Source: "dist\ClaudeUsageTray\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"""; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\ClaudeUsageTray"

[Code]
const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';
  AppMutex = 'Local\claude-usage-tray';
  QuitEvent = 'Local\claude-usage-tray-quit';
  SYNCHRONIZE = $00100000;
  EVENT_MODIFY_STATE = $0002;

function OpenMutex(dwDesiredAccess: Cardinal; bInheritHandle: Integer; lpName: String): THandle;
  external 'OpenMutexW@kernel32.dll stdcall';
function OpenEvent(dwDesiredAccess: Cardinal; bInheritHandle: Integer; lpName: String): THandle;
  external 'OpenEventW@kernel32.dll stdcall';
function SetEvent(hEvent: THandle): Integer;
  external 'SetEvent@kernel32.dll stdcall';
function CloseHandle(hObject: THandle): Integer;
  external 'CloseHandle@kernel32.dll stdcall';

function AppRunning: Boolean;
var
  Handle: THandle;
begin
  Handle := OpenMutex(SYNCHRONIZE, 0, AppMutex);
  Result := Handle <> 0;
  if Result then
    CloseHandle(Handle);
end;

function WaitForAppExit(Tries: Integer): Boolean;
var
  I: Integer;
begin
  for I := 1 to Tries do
  begin
    if not AppRunning then
    begin
      Result := True;
      Exit;
    end;
    Sleep(100);
  end;
  Result := not AppRunning;
end;

procedure StopApp;
var
  Handle: THandle;
  ResultCode: Integer;
begin
  if not AppRunning then
    Exit;
  Handle := OpenEvent(EVENT_MODIFY_STATE, 0, QuitEvent);
  if Handle <> 0 then
  begin
    SetEvent(Handle);
    CloseHandle(Handle);
    if WaitForAppExit(100) then
      Exit;
  end;
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  WaitForAppExit(50);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopApp;
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    StopApp;
    RegDeleteValue(HKEY_CURRENT_USER, RunKey, '{#AppName}');
  end;
end;
