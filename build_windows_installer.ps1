$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    $python = 'python'
}

try {
    & $python -c "import PyInstaller" *> $null
} catch {
    & $python -m pip install pyinstaller
}

try {
    Get-Process -Name 'AIWriteX' -ErrorAction SilentlyContinue | Stop-Process -Force
} catch {}
Start-Sleep -Milliseconds 500

if (Test-Path '.\build') {
    Remove-Item '.\build' -Recurse -Force -ErrorAction SilentlyContinue
}
if (Test-Path '.\dist\AIWriteX') {
    cmd /c rmdir /s /q ".\dist\AIWriteX"
}

& $python -m PyInstaller '.\aiwritex_windows.spec' --noconfirm
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$iscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
if (Test-Path $iscc) {
    & $iscc '.\aiwritex_installer.iss'
} else {
    Write-Host 'Inno Setup not found. onedir build completed. Install Inno Setup 6 and rerun this script for Setup.exe.'
}
