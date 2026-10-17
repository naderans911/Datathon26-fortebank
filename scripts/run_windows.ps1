# Local services by default. Add -Public to create an HTTPS jury URL.
param([switch]$Public, [switch]$Review, [switch]$Restart)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$taskPython = (Resolve-Path '.venv\Scripts\python.exe').Path
$taskArguments = @('scripts/serve.py', $(if ($Restart) { 'restart' } else { 'start' }))
if ($Public) { $taskArguments += '--public' }
if ($Review) { $taskArguments += '--review' }
& $taskPython @taskArguments
exit $LASTEXITCODE
