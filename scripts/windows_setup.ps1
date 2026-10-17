# One-time setup on Windows 10/11. Run from the repo root in PowerShell:
#   powershell -ExecutionPolicy Bypass -File scripts\windows_setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

Write-Host ">> Installing Python 3.13, FFmpeg, cloudflared (winget)"
foreach ($id in "Python.Python.3.13", "Gyan.FFmpeg", "Cloudflare.cloudflared") {
    winget install --id $id -e --silent --accept-source-agreements --accept-package-agreements
    # exit code != 0 also means "already installed"; the checks below catch real failures
}
Refresh-Path
foreach ($tool in "ffmpeg", "ffprobe", "cloudflared") {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "$tool is not on PATH. Close this window, open a new PowerShell and run the script again."
    }
}

Write-Host ">> Python virtual environment + packages (a few minutes)"
if (-not (Test-Path .venv)) { py -3.13 -m venv .venv }
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install -q --upgrade pip
& $py -m pip install -q -r requirements.in -r requirements-ml.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host ">> Creating .env (generates the jury API key)"
& $py scripts\setup_env.py
& $py -c "import re,pathlib; p=pathlib.Path('.env'); p.write_text(re.sub(r'(?m)^RETENTION_HOURS=[ \t]*$', 'RETENTION_HOURS=72', p.read_text(encoding='utf-8')), encoding='utf-8')"

Write-Host ">> Downloading model weights (one time, ~160 MB)"
& $py scripts\download_models.py
if ($LASTEXITCODE -ne 0) { throw "model download failed" }

Write-Host ">> Speed check (about 1 minute)"
& $py scripts\benchmark.py

Write-Host ">> Keeping the PC awake while plugged in"
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0

Write-Host ""
Write-Host "DONE. Now start the service:  powershell -ExecutionPolicy Bypass -File scripts\run_windows.ps1"
Write-Host "Jury API key:"
(Select-String -Path .env -Pattern "^JURY_API_KEY=").Line
