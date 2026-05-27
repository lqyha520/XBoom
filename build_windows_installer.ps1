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
    Get-Process -Name 'XBoom' -ErrorAction SilentlyContinue | Stop-Process -Force
} catch {}
Start-Sleep -Milliseconds 500

if (Test-Path '.\build') {
    Remove-Item '.\build' -Recurse -Force -ErrorAction SilentlyContinue
}
if (Test-Path '.\dist\XBoom') {
    cmd /c rmdir /s /q ".\dist\XBoom"
}

& $python -m PyInstaller '.\aiwritex_windows.spec' --noconfirm
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$isccCandidates = @(
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    'C:\Program Files\Inno Setup 6\ISCC.exe',
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
)

$iscc = $isccCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) {
    $isccCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($isccCommand) {
        $iscc = $isccCommand.Source
    }
}

if ($iscc) {
    & $iscc '.\aiwritex_installer.iss'
} else {
    Write-Host 'Inno Setup not found. onedir build completed. Install Inno Setup 6 and rerun this script for Setup.exe.'
}
