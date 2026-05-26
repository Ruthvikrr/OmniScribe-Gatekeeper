$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pidFile = Join-Path $root "outputs\omniscribe.pid"

if (Test-Path -LiteralPath $pidFile) {
    $pidValue = Get-Content -LiteralPath $pidFile | Select-Object -First 1
    if ($pidValue) {
        Stop-Process -Id ([int]$pidValue) -Force
    }
    Remove-Item -LiteralPath $pidFile -Force
}

$listeners = netstat -ano | Select-String ":7860\s+.*LISTENING"
foreach ($line in $listeners) {
    $parts = ($line.ToString() -split "\s+") | Where-Object { $_ }
    $owningPid = $parts[-1]
    Stop-Process -Id ([int]$owningPid) -Force
}

Write-Host "Stopped OmniScribe Gatekeeper."
