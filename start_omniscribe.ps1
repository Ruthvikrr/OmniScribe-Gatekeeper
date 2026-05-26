$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$outputs = Join-Path $root "outputs"
$out = Join-Path $outputs "omniscribe.out.log"
$err = Join-Path $outputs "omniscribe.err.log"
$pidFile = Join-Path $outputs "omniscribe.pid"
$python = Join-Path $root ".venv\Scripts\python.exe"
$app = Join-Path $root "app.py"

New-Item -ItemType Directory -Force -Path $outputs | Out-Null

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python was not found at $python. Recreate the virtual environment first."
}

$existing = netstat -ano | Select-String ":7860\s+.*LISTENING"
if ($existing) {
    Write-Host "OmniScribe is already running at http://127.0.0.1:7860"
    Write-Host $existing
    return
}

Set-Content -LiteralPath $out -Value ""
Set-Content -LiteralPath $err -Value ""

$process = Start-Process `
    -FilePath $python `
    -ArgumentList @("-u", $app) `
    -WorkingDirectory $root `
    -RedirectStandardOutput $out `
    -RedirectStandardError $err `
    -WindowStyle Hidden `
    -PassThru

Set-Content -LiteralPath $pidFile -Value $process.Id

$deadline = (Get-Date).AddSeconds(90)
$ready = $false
$lastStatus = ""

while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2

    $running = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
    if (-not $running) {
        Write-Host "OmniScribe exited before it opened port 7860."
        Write-Host "STDOUT:"
        Get-Content -LiteralPath $out -Tail 80 -ErrorAction SilentlyContinue
        Write-Host "STDERR:"
        Get-Content -LiteralPath $err -Tail 80 -ErrorAction SilentlyContinue
        exit 1
    }

    try {
        $lastStatus = (Invoke-WebRequest -Uri "http://127.0.0.1:7860" -UseBasicParsing -TimeoutSec 5).StatusCode
        if ($lastStatus -eq 200) {
            $ready = $true
            break
        }
    } catch {
        $lastStatus = $_.Exception.Message
    }
}

if (-not $ready) {
    Write-Host "OmniScribe process is running, but http://127.0.0.1:7860 did not become ready."
    Write-Host "PID: $($process.Id)"
    Write-Host "Last HTTP check: $lastStatus"
    Write-Host "STDERR:"
    Get-Content -LiteralPath $err -Tail 80 -ErrorAction SilentlyContinue
    exit 1
}

Write-Host "OmniScribe is running."
Write-Host "PID: $($process.Id)"
Write-Host "Open: http://127.0.0.1:7860"
Write-Host "Logs: $out and $err"
