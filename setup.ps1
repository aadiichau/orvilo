param([switch]$SkipRuntime)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        & py -3 -c "import sys, struct; assert sys.version_info >= (3,11), 'Python 3.11 or newer is required'; assert struct.calcsize('P') == 8, 'Install 64-bit Python'"
        if ($LASTEXITCODE -ne 0) { throw 'Install 64-bit Python 3.11 or newer from python.org, then run setup again.' }
        & py -3 -m venv .venv
    } else {
        & python -c "import sys, struct; assert sys.version_info >= (3,11), 'Python 3.11 or newer is required'; assert struct.calcsize('P') == 8, 'Install 64-bit Python'"
        if ($LASTEXITCODE -ne 0) { throw 'Install 64-bit Python 3.11 or newer from python.org, then run setup again.' }
        & python -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the local Python environment.' }
}
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Dependency installer update failed. Check your internet connection.' }
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $python scripts\export_icons.py
if ($LASTEXITCODE -ne 0) { throw 'Icon export failed.' }
if (-not $SkipRuntime) {
    & $python scripts\bootstrap_runtime.py
    if ($LASTEXITCODE -ne 0) { throw 'Runtime download failed. Run setup again or see README for manual setup.' }
}
Write-Host 'Orvilo is ready. Run: .\run.ps1' -ForegroundColor Green
