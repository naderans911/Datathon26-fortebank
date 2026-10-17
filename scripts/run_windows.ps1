# Start API + worker + public tunnel on Windows. Keep this window open; close it to stop.
#   powershell -ExecutionPolicy Bypass -File scripts\run_windows.ps1
# Safe to re-run: stale instances from a previous start are stopped first.
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:HF_HUB_OFFLINE = "1"; $env:TRANSFORMERS_OFFLINE = "1"
# Detector stride chosen by scripts\benchmark.py (read from the environment, not by the settings loader).
$stride = Select-String -Path .env -Pattern "^CV_DET_STRIDE=(\d+)" | Select-Object -First 1
if ($stride) { $env:CV_DET_STRIDE = $stride.Matches[0].Groups[1].Value; Write-Host "CV_DET_STRIDE=$env:CV_DET_STRIDE" }
$py = (Resolve-Path ".\.venv\Scripts\python.exe").Path
New-Item -ItemType Directory -Force logs | Out-Null

Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match "backend\.app\.(main|workers\.runner)" -or $_.Name -eq "cloudflared.exe" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep 1
Remove-Item logs\public_url.txt -ErrorAction SilentlyContinue

$api = Start-Process $py -WindowStyle Hidden -PassThru `
    -ArgumentList "-m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=*" `
    -RedirectStandardOutput logs\api.out.log -RedirectStandardError logs\api.log
$worker = Start-Process $py -WindowStyle Hidden -PassThru -ArgumentList "-m backend.app.workers.runner" `
    -RedirectStandardOutput logs\worker.out.log -RedirectStandardError logs\worker.log
Write-Host "Local:  http://127.0.0.1:8000"

try {
    # Restart the quick tunnel if it drops; every restart gets a NEW public URL.
    while (-not $api.HasExited) {
        Remove-Item logs\cloudflared.log -ErrorAction SilentlyContinue
        $tunnel = Start-Process cloudflared -WindowStyle Hidden -PassThru `
            -ArgumentList "tunnel --url http://127.0.0.1:8000" `
            -RedirectStandardOutput logs\cloudflared.out.log -RedirectStandardError logs\cloudflared.log
        $url = $null
        while (-not $tunnel.HasExited) {
            if (-not $url -and (Test-Path logs\cloudflared.log)) {
                $m = Select-String -Path logs\cloudflared.log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
                if ($m) {
                    $url = $m.Matches[0].Value
                    Set-Content logs\public_url.txt $url
                    Write-Host ""
                    Write-Host "Public URL (give this to the jury): $url" -ForegroundColor Green
                }
            }
            if ($worker.HasExited) {
                Write-Host "Worker stopped; restarting it..."
                $worker = Start-Process $py -WindowStyle Hidden -PassThru -ArgumentList "-m backend.app.workers.runner" `
                    -RedirectStandardOutput logs\worker.out.log -RedirectStandardError logs\worker.log
            }
            Start-Sleep 2
        }
        Write-Host "Tunnel stopped; restarting in 5 s (the public URL will change)..."
        Start-Sleep 5
    }
    Write-Host "API stopped - see logs\api.log"
} finally {
    foreach ($p in $api, $worker, $tunnel) { if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }
}
