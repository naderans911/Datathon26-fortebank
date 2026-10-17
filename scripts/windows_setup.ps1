# Install project dependencies. Models and public tunneling are explicit options.
param([switch]$WithModels)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -3.13 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 is required.' }
}
$taskPython = (Resolve-Path '.venv\Scripts\python.exe').Path
& $taskPython -m pip install -r requirements.lock -r requirements-training.txt
if ($LASTEXITCODE -ne 0) { throw 'Base dependency installation failed.' }
& $taskPython scripts/setup_env.py
if ($LASTEXITCODE -ne 0) { throw 'Private environment setup failed.' }
if ($WithModels) {
    & $taskPython -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.9.1 torchvision==0.24.1
    if ($LASTEXITCODE -ne 0) { throw 'CPU inference installation failed.' }
    & $taskPython -m pip install -r requirements-ml.txt
    if ($LASTEXITCODE -ne 0) { throw 'ML dependency installation failed.' }
    & $taskPython scripts/download_models.py
    if ($LASTEXITCODE -ne 0) { throw 'Official model download failed.' }
}
if (Get-Command npm.cmd -ErrorAction SilentlyContinue) {
    npm.cmd --prefix frontend ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    npm.cmd --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} else {
    throw 'Node.js and npm.cmd are required to build the frontend. Install Node.js 24 and rerun setup.'
}
& $taskPython scripts/preflight.py
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed. Resolve prerequisites before starting services.' }
Write-Host 'Setup complete. Follow README for private model, label and jury configuration.'
Write-Host 'Start local services: .\.venv\Scripts\python.exe scripts/serve.py start'
