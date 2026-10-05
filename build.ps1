param([switch]$Installer)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run .\setup.ps1 first.' }
& $python scripts\export_icons.py
if ($LASTEXITCODE -ne 0) { throw 'Icon export failed.' }
& $python scripts\collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'License collection failed.' }
& $python scripts\collect_sources.py
if ($LASTEXITCODE -ne 0) { throw 'Dependency source inventory failed.' }
& $python -m PyInstaller --clean --noconfirm Orvilo.spec
if ($LASTEXITCODE -ne 0) { throw 'The application build failed.' }
if ($Installer) {
    $compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if (-not $compiler) {
        $candidate = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
        if (Test-Path -LiteralPath $candidate) { $compiler = Get-Item -LiteralPath $candidate }
    }
    if (-not $compiler) { throw 'Install Inno Setup 6, or use the portable dist\Orvilo.exe.' }
    & $compiler.FullName installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
}
Write-Host 'Build complete: dist\Orvilo.exe' -ForegroundColor Green
