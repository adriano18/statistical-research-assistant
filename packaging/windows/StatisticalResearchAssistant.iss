; Statistical Research Assistant: Windows installer (Stage 35, issue #44).
;
; Built by tools/build_installer.py from the `flet build windows` folder:
;   ISCC /DAppVersion=1.0.0 /DNumericVersion=1.0.0.0 /DSourceDir=<bundle> ^
;        /DOutputDir=<dist> StatisticalResearchAssistant.iss
;
; - Per-user installation without administrator rights (all users on request).
; - One AppId for every version: an update replaces the installed program.
; - Research data never lives in the program folder: it is kept in
;   %LOCALAPPDATA%\StatisticalResearchAssistant (see app_paths.py). Updates
;   and uninstalling leave it alone; the uninstaller deletes it only after
;   two explicit confirmations, and never in silent mode.
; - The application holds the named mutex below while it runs; setup waits
;   for it to close (in-app update) or asks the researcher to close it.

#ifndef AppVersion
  #error Define AppVersion (for example /DAppVersion=1.0.0)
#endif
#ifndef NumericVersion
  #error Define NumericVersion (four numbers, for example /DNumericVersion=1.0.0.0)
#endif
#ifndef SourceDir
  #error Define SourceDir: the folder that holds StatisticalResearchAssistant.exe
#endif
#ifndef OutputDir
  #define OutputDir "dist"
#endif
#ifndef Compression
  #define Compression "lzma2/max"
#endif
#ifndef Publisher
  #define Publisher "Statistical Research Assistant"
#endif

#define AppName "Statistical Research Assistant"
#define AppExe "StatisticalResearchAssistant.exe"
#define AppMutex "StatisticalResearchAssistant.Running"
#define DataFolder "StatisticalResearchAssistant"
#define Repository "https://github.com/adriano18/statistical-research-assistant"

[Setup]
; Never change the AppId (app_identity.INSTALLER_APP_ID).
AppId={{8467540D-B8DC-4046-A878-0EE29F330E63}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#Publisher}
AppPublisherURL={#Repository}
AppSupportURL={#Repository}/issues
AppUpdatesURL={#Repository}/releases
AppCopyright=Copyright (c) 2026 {#Publisher}
VersionInfoVersion={#NumericVersion}
VersionInfoProductVersion={#NumericVersion}
VersionInfoProductTextVersion={#AppVersion}
VersionInfoDescription={#AppName} setup
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
UsePreviousAppDir=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
; "x64" is understood by every Inno Setup 6 release on the runners.
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=StatisticalResearchAssistant-{#AppVersion}-Setup
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression={#Compression}
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
; The researcher closes the application (or the application closes itself
; for an update); setup never terminates it.
CloseApplications=no
RestartApplications=no
SetupLogging=yes
AllowNoIcons=yes
#ifdef SignTool
SignTool={#SignTool}
SignedUninstaller=yes
#endif

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[CustomMessages]
en.CloseAppFirst=Statistical Research Assistant is running.%n%nSave your work, close the application, then choose Retry.
ru.CloseAppFirst=Statistical Research Assistant запущен.%n%nСохраните работу, закройте приложение и нажмите «Повтор».
en.UpdateWaitFailed=Statistical Research Assistant did not close, so the update was not installed. Your data is unchanged.
ru.UpdateWaitFailed=Statistical Research Assistant не закрылся, поэтому обновление не установлено. Ваши данные не изменены.
en.AskDeleteData=Statistical Research Assistant will be removed from this computer.%n%nYour research projects, questionnaires, responses and backups are kept in:%n%1%n%nDo you ALSO want to delete this research data?%n%nChoose No to keep it (recommended): a later installation finds it again.
ru.AskDeleteData=Statistical Research Assistant будет удалён с этого компьютера.%n%nВаши исследовательские проекты, анкеты, ответы и резервные копии хранятся в папке:%n%1%n%nУдалить ТАКЖЕ эти исследовательские данные?%n%nНажмите «Нет», чтобы сохранить их (рекомендуется): после повторной установки они снова будут доступны.
en.ConfirmDeleteData=Permanently delete ALL research data in%n%1?%n%nProjects, questionnaires, responses, reports and backups in this folder cannot be recovered. Choose Yes only if you have your own copy.
ru.ConfirmDeleteData=Безвозвратно удалить ВСЕ исследовательские данные в папке%n%1?%n%nПроекты, анкеты, ответы, отчёты и резервные копии из этой папки восстановить будет невозможно. Нажмите «Да», только если у вас есть собственная копия.
en.DeleteDataFailed=Some research data could not be deleted. It is still in %1.
ru.DeleteDataFailed=Часть исследовательских данных удалить не удалось. Они остались в папке %1.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

; generated-layout.iss (tools/build_installer.py) lists the program's own
; top-level files and folders: [InstallDelete] removes the previous
; version's copies before an update (no stale Python packages), and
; [UninstallDelete] removes what the program created inside them at run time.
; Neither ever names the program folder's "app\data" (questionnaires of very
; old portable previews), which is kept and offered for copying instead.
#include "generated-layout.iss"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent runasoriginaluser
; In-app update: start the new version again once it is installed.
Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: RelaunchAfterUpdate

[UninstallDelete]
Type: dirifempty; Name: "{app}\app"
Type: dirifempty; Name: "{app}"

[Code]
var
  DeleteResearchData: Boolean;

function HasSwitch(const Name: string): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), Name) = 0 then
    begin
      Result := True;
      Exit;
    end;
end;

{ /UPDATEFROMAPP: the running application started this installer and is
  closing itself; wait for it, then start the new version. }
function UpdateFromApp: Boolean;
begin
  Result := HasSwitch('/UPDATEFROMAPP');
end;

function RelaunchAfterUpdate: Boolean;
begin
  Result := UpdateFromApp;
end;

function AppRunning: Boolean;
begin
  Result := CheckForMutexes('{#AppMutex}');
end;

function WaitForAppToClose(Seconds: Integer): Boolean;
var
  Waited: Integer;
begin
  Waited := 0;
  while AppRunning and (Waited < Seconds * 4) do
  begin
    Sleep(250);
    Waited := Waited + 1;
  end;
  Result := not AppRunning;
end;

function AskToClose: Boolean;
begin
  Result := True;
  while AppRunning do
    if SuppressibleMsgBox(CustomMessage('CloseAppFirst'), mbError, MB_RETRYCANCEL, IDCANCEL) <> IDRETRY then
    begin
      Result := False;
      Exit;
    end;
end;

function InitializeSetup: Boolean;
begin
  if UpdateFromApp then
  begin
    Result := WaitForAppToClose(120);
    if not Result then
    begin
      Log('The application did not close within 120 seconds; nothing was installed.');
      SuppressibleMsgBox(CustomMessage('UpdateWaitFailed'), mbError, MB_OK, IDOK);
    end;
  end
  else
    Result := AskToClose;
end;

function InitializeUninstall: Boolean;
begin
  Result := AskToClose;
end;

function ResearchDataFolder: string;
begin
  Result := ExpandConstant('{localappdata}\{#DataFolder}');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Folder: string;
begin
  Folder := ResearchDataFolder;
  if CurUninstallStep = usUninstall then
  begin
    DeleteResearchData := False;
    { Never asked in silent mode: a silent uninstall always keeps the data. }
    if (not UninstallSilent) and DirExists(Folder) then
      if MsgBox(FmtMessage(CustomMessage('AskDeleteData'), [Folder]), mbConfirmation,
                MB_YESNO or MB_DEFBUTTON2) = IDYES then
        if MsgBox(FmtMessage(CustomMessage('ConfirmDeleteData'), [Folder]), mbError,
                  MB_YESNO or MB_DEFBUTTON2) = IDYES then
          DeleteResearchData := True;
    if DeleteResearchData then
      Log('The researcher confirmed twice that the research data folder is to be deleted.')
    else
      Log('Research data kept: ' + Folder);
  end;
  if (CurUninstallStep = usPostUninstall) and DeleteResearchData then
  begin
    if DelTree(Folder, True, True, True) then
      Log('Research data folder deleted on request: ' + Folder)
    else
      MsgBox(FmtMessage(CustomMessage('DeleteDataFailed'), [Folder]), mbError, MB_OK);
  end;
end;
