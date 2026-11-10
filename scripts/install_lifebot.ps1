# Installs the Lifebot desktop app: dependencies, icon, and Desktop + Start Menu shortcuts.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install_lifebot.ps1
#
# Safe to re-run. It only creates/updates two shortcut files (Lifebot.lnk) and runs `npm install`
# inside apps\lifebot when Electron is missing. The app registers "start with Windows" itself on its
# first launch (toggle it in Reminders > Notifications and startup, or from the tray menu).
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$app  = Join-Path $repo 'apps\lifebot'
$exe  = Join-Path $app 'node_modules\electron\dist\electron.exe'
$icon = Join-Path $app 'assets\icon.ico'

if (-not (Test-Path $exe)) {
    Write-Host 'Installing Electron (one-time)...'
    Push-Location $app
    try { npm install --no-audit --no-fund } finally { Pop-Location }
    if (-not (Test-Path $exe)) { throw "Electron was not installed at $exe" }
}

if (-not (Test-Path $icon)) {
    Write-Host 'Generating icon...'
    python (Join-Path $app 'assets\make_icon.py')
}

# ELECTRON_RUN_AS_NODE makes electron.exe behave as plain Node and the app would not open
if ($env:ELECTRON_RUN_AS_NODE) {
    Write-Warning 'ELECTRON_RUN_AS_NODE is set in this session; shortcuts are unaffected, but do not set it globally.'
}

$shell = New-Object -ComObject WScript.Shell
$targets = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Lifebot.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'Lifebot.lnk')
)
foreach ($path in $targets) {
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath       = $exe
    $lnk.Arguments        = '"' + $app + '"'
    $lnk.WorkingDirectory = $app
    $lnk.IconLocation     = "$icon,0"
    $lnk.Description      = 'Lifebot: chat, typewriter tasks, Pomodoro and reminders'
    $lnk.Save()
    Write-Host "Shortcut: $path"
}

Write-Host ''
Write-Host 'Done. Double-click "Lifebot" on your Desktop to start it.'
Write-Host 'Closing the window keeps it running in the system tray so reminders still fire.'
