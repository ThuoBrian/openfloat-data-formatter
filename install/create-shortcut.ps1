# Creates (or refreshes) the "OpenFloat Data Formatter" shortcuts on the
# Desktop and in the user's Start menu, with the app's icon. Both point at
# run.bat in the app folder this script lives in.
#
# install.ps1 runs this after every install or update. To add the shortcuts to
# an existing install, or to a developer checkout (`just shortcut`):
#
#   powershell -ExecutionPolicy Bypass -File install\create-shortcut.ps1
#
# 'Programs' is the user's own Start menu folder, so no admin rights are needed.
# Exit code 1 means at least one shortcut could not be made; run.bat still
# starts the app either way.

param(
    [string]$AppDir = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

$runBat = Join-Path $AppDir 'run.bat'
$icon   = Join-Path $AppDir 'install\openfloat.ico'
if (-not (Test-Path $runBat)) {
    Write-Host "run.bat not found in $AppDir - is this the app folder?" -ForegroundColor Red
    exit 1
}

$shell  = New-Object -ComObject WScript.Shell
$failed = $false
foreach ($folder in [Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs')) {
    try {
        $link = $shell.CreateShortcut((Join-Path $folder 'OpenFloat Data Formatter.lnk'))
        $link.TargetPath       = $runBat
        $link.WorkingDirectory = $AppDir
        $link.Description      = 'Start OpenFloat Data Formatter'
        # The icon is optional: without it Windows shows the batch-file icon,
        # which still works, so a missing file must not stop the shortcut.
        if (Test-Path $icon) { $link.IconLocation = "$icon,0" }
        $link.Save()
    }
    catch {
        $failed = $true
        Write-Host "Couldn't create a shortcut in $folder - start the app with run.bat in $AppDir" -ForegroundColor Cyan
    }
}

if ($failed) { exit 1 }
Write-Host "Added an 'OpenFloat Data Formatter' shortcut to your Desktop and Start menu." -ForegroundColor Green
