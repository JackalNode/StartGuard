; startguard_installer.iss
; Inno Setup script for StartGuard v0.9.0
;
; HOW TO USE:
;   1. Open Inno Setup Compiler
;   2. File > Open > select this file
;   3. Click Build > Compile (or press F9)
;   4. Your installer will appear in the Output folder below

#define AppName "StartGuard"
#define AppVersion "0.9.0"
#define AppPublisher "JackalNode"
#define AppURL "https://jackalnode.com"
#define AppExeName "StartGuard.exe"

; IMPORTANT: Update this path to match where PyInstaller put your build
; After running pyinstaller startguard.spec, the built files will be here:
#define SourceDir SourcePath + "dist\StartGuard"

[Setup]
; Unique ID for this app — DO NOT change this after first release
; It's how Windows identifies StartGuard in Add/Remove Programs
; Generated fresh for StartGuard — safe to use as-is
AppId={{7F3A2C1E-4B8D-4F2A-9E6C-1D3A5B7C9E2F}

AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}

; Where the app installs to by default
; {autopf} = C:\Program Files on 64-bit Windows, resolves automatically
DefaultDirName={autopf}\JackalNode\StartGuard
DefaultGroupName=JackalNode\StartGuard

; Where the finished installer .exe gets saved after compiling
OutputDir={#SourcePath}Output
OutputBaseFilename=StartGuard_Setup_v0.9.0

; Require admin rights to install (needed since the app itself needs admin)
PrivilegesRequired=admin

; Compression — solid gives best file size reduction
Compression=lzma2/ultra64
SolidCompression=yes

; Minimum Windows version: Windows 10 (version 10.0)
; This blocks installation on Windows 7/8 with a friendly message
MinVersion=10.0

; Architecture: 64-bit only
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

; Installer appearance
WizardStyle=modern
SetupIconFile=

; Show a licence/info page? Set to yes if you add a licence file later
LicenseFile=
InfoBeforeFile=
InfoAfterFile=

; Uninstall settings
UninstallDisplayName=StartGuard
UninstallDisplayIcon={app}\{#AppExeName}
CreateUninstallRegKey=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; These are tick-box options shown to the user during install
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; Copy everything from the PyInstaller output folder into the install directory
; {app} = the install location the user chose (e.g. C:\Program Files\JackalProducts\StartGuard)
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start menu shortcut
Name: "{group}\StartGuard"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall StartGuard"; Filename: "{uninstallexe}"

; Desktop shortcut — only created if the user ticked the box during install
Name: "{autodesktop}\StartGuard"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch StartGuard now (requires admin)"; Flags: nowait postinstall skipifsilent shellexec runascurrentuser

[UninstallDelete]
; DELETE EVERYTHING on uninstall — app folder, all files, no leftovers
Type: filesandordirs; Name: "{app}"

; Also wipe the user's settings from AppData
; {localappdata} = C:\Users\YourUsername\AppData\Local
Type: filesandordirs; Name: "{localappdata}\JackalNode\StartGuard"

; And roaming AppData just in case anything ended up there
Type: filesandordirs; Name: "{userappdata}\StartGuard"

[Registry]
; Clean up the app's registry entries on uninstall
; This removes the single-instance lock port entry if we ever write one
Root: HKCU; Subkey: "Software\JackalNode\StartGuard"; Flags: uninsdeletekey

[Messages]
FinishedLabel=StartGuard has been installed successfully.%nUse the Start menu shortcut to open it.

[Code]
// This runs before install starts
// Checks Windows version and blocks install on Win 7/8 with a plain-English message
function InitializeSetup(): Boolean;
begin
  if GetWindowsVersion < $0A000000 then
  begin
    MsgBox(
      'StartGuard requires Windows 10 or later.' + #13 +
      'Your PC is running an older version of Windows that is no longer supported.' + #13 +
      'Please upgrade to Windows 10 or 11 to use StartGuard.',
      mbError, MB_OK
    );
    Result := False;
  end
  else
    Result := True;
end;
