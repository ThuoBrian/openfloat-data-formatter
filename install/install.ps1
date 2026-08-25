$ErrorActionPreference = 'Stop'

$Repo    = 'ThuoBrian/openfloat-data-formatter'
$Branch  = 'main'
$AppName = 'openfloat-data-formatter'
$DataRel = '.env'

$green = @{ ForegroundColor = 'Green' }
$cyan  = @{ ForegroundColor = 'Cyan' }

function Get-InstallRoot {
    # Ask which parent folder to install into; the app folder is created inside it.
    # An explicit override wins and skips the prompt (scriptable / non-interactive).
    if ($env:OFDF_INSTALL_DIR) { return $env:OFDF_INSTALL_DIR }

    $desktop = [Environment]::GetFolderPath('Desktop')

    # Preferred: a graphical "Browse For Folder" dialog.
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
        $dlg.Description = "Choose where to install OpenFloat Data Formatter (an 'openfloat-data-formatter' folder will be created inside)."
        $dlg.ShowNewFolderButton = $true
        try { $dlg.SelectedPath = $desktop } catch { }
        # Owned by a TopMost form so the dialog appears in front of the console.
        $owner  = New-Object System.Windows.Forms.Form -Property @{ TopMost = $true }
        $result = $dlg.ShowDialog($owner)
        $owner.Dispose()
        if ($result -eq [System.Windows.Forms.DialogResult]::OK -and $dlg.SelectedPath) {
            return $dlg.SelectedPath
        }
        Write-Host "No folder chosen - installing to the Desktop." @cyan
        return $desktop
    }
    catch {
        # Fallback for hosts without a usable WinForms dialog (e.g. PowerShell 7
        # running MTA, or a headless session): a simple numbered menu.
        Write-Host ""
        Write-Host "Where should OpenFloat Data Formatter be installed?"
        Write-Host "  [1] Desktop (default)"
        Write-Host "  [2] Documents"
        Write-Host "  [3] Home folder"
        Write-Host "  [4] Type a path"
        switch (Read-Host "Enter 1-4 (or press Enter for Desktop)") {
            '2' { return [Environment]::GetFolderPath('MyDocuments') }
            '3' { return [Environment]::GetFolderPath('UserProfile') }
            '4' {
                $p = Read-Host "Full path to the folder to install into"
                if ([string]::IsNullOrWhiteSpace($p)) { return $desktop } else { return $p }
            }
            default { return $desktop }
        }
    }
}

Write-Host ""
Write-Host "OpenFloat Data Formatter - installer" @green

$InstallRoot = Get-InstallRoot
$Target      = Join-Path $InstallRoot $AppName

Write-Host "Installing to: $Target" @green
Write-Host ""

# 1. Download the current source as a zip (works for a public repo, no login).
$zipUrl     = "https://github.com/$Repo/archive/refs/heads/$Branch.zip"
$tmpZip     = Join-Path $env:TEMP "$AppName-$Branch.zip"
$tmpExtract = Join-Path $env:TEMP "$AppName-extract"

Write-Host "Downloading the latest version..." @cyan
Invoke-WebRequest -Uri $zipUrl -OutFile $tmpZip -UseBasicParsing

# 2. Extract (the zip contains a single top-level <repo>-<branch> folder).
if (Test-Path $tmpExtract) { Remove-Item $tmpExtract -Recurse -Force }
Expand-Archive -Path $tmpZip -DestinationPath $tmpExtract -Force
$extracted = Get-ChildItem $tmpExtract -Directory | Select-Object -First 1

# 3. Preserve a local .env (custom thresholds, etc.) - it is intentionally not
#    shipped in the repo, so a plain re-download would otherwise wipe it.
$savedData = $null
$existingData = Join-Path $Target $DataRel
if (Test-Path $existingData) {
    Write-Host "Preserving your existing .env settings..." @cyan
    $savedData = Join-Path $env:TEMP '.env.bak'
    Copy-Item $existingData $savedData -Force
}

# 4. Put the new version in place (step out of the folder before replacing it).
Set-Location $InstallRoot
if (Test-Path $Target) { Remove-Item $Target -Recurse -Force }
Move-Item $extracted.FullName $Target
if ($savedData) {
    Copy-Item $savedData (Join-Path $Target $DataRel) -Force
    Remove-Item $savedData -Force -ErrorAction SilentlyContinue
}

# 5. Tidy up temp files.
Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue
Remove-Item $tmpExtract -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Done. Starting the app (first run sets up the environment)..." @green
Write-Host ""

# 6. Launch. run.bat resolves its own location, so cwd does not matter.
Set-Location $Target
& (Join-Path $Target 'run.bat')
