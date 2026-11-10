# Starts the OmniRoute server (if needed), waits until it is really healthy, retrying until it is,
# then runs the commands in the Desktop file (Claude Code through OmniRoute). The API key stays in that file.
param([string]$CmdFile = (Join-Path $env:USERPROFILE 'OneDrive\Desktop\omniroute_apiLogin.txt'))

$health = 'http://localhost:20128/api/monitoring/health'
$maxMinutes = 10          # give up (and say so) after this long
$restartAfterSec = 120    # if the server window died, start it again

function Test-Healthy {
    try { return (Invoke-WebRequest $health -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 } catch { return $false }
}
function Test-Port { return (Test-NetConnection localhost -Port 20128 -WarningAction SilentlyContinue).TcpTestSucceeded }
function Start-Server { Start-Process powershell -ArgumentList '-NoExit', '-Command', 'omniroute' | Out-Null }

if (-not (Test-Path -LiteralPath $CmdFile)) { Write-Host "Missing $CmdFile" -ForegroundColor Red; exit 1 }

$sw = [Diagnostics.Stopwatch]::StartNew()
$lastStart = $sw.Elapsed
if (Test-Healthy) {
    Write-Host 'OmniRoute is already running.' -ForegroundColor Green
} else {
    if (-not (Test-Port)) { Write-Host 'Starting the OmniRoute server...'; Start-Server } else { Write-Host 'OmniRoute is starting up...' }
    while (-not (Test-Healthy)) {
        if ($sw.Elapsed.TotalMinutes -ge $maxMinutes) {
            Write-Host "OmniRoute did not become healthy in $maxMinutes minutes. Check its server window, then run this again." -ForegroundColor Red
            exit 2
        }
        # the server's own "did not respond in 60s" message is often just slow startup; only restart if nothing is listening
        if (-not (Test-Port) -and ($sw.Elapsed - $lastStart).TotalSeconds -ge $restartAfterSec) {
            Write-Host 'Server is not listening - starting it again...' -ForegroundColor Yellow
            Start-Server
            $lastStart = $sw.Elapsed
        }
        Write-Host ("Waiting for OmniRoute... {0}s" -f [int]$sw.Elapsed.TotalSeconds)
        Start-Sleep -Seconds 3
    }
    Write-Host 'OmniRoute is up.' -ForegroundColor Green
}

Invoke-Expression (Get-Content -Raw -LiteralPath $CmdFile)
