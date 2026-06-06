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

Write-Host 'Exporting factory config (no personal settings)...' -ForegroundColor Cyan
& $python '.\scripts\export_factory_config_for_build.py'
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $python -m PyInstaller '.\aiwritex_windows.spec' --noconfirm
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host 'Verifying dist bundle has no personal API keys...' -ForegroundColor Cyan
$distRoot = Join-Path $PSScriptRoot 'dist\小爆来咯'
$badHits = @()
if (Test-Path $distRoot) {
    Get-ChildItem -Path $distRoot -Recurse -Include '*.yaml','*.yml','*.toml','*.json' -File -ErrorAction SilentlyContinue | ForEach-Object {
        $content = Get-Content -LiteralPath $_.FullName -Raw -ErrorAction SilentlyContinue
        if ($content -match 'sk-[A-Za-z0-9]{16,}') {
            $badHits += $_.FullName
        }
        if ($content -match 'wx[a-z0-9]{16}') {
            $badHits += $_.FullName
        }
    }
}
if ($badHits.Count -gt 0) {
    Write-Host '[ERROR] Personal secrets found in dist bundle:' -ForegroundColor Red
    $badHits | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    exit 1
}
Write-Host '[OK] dist bundle contains no detected API keys' -ForegroundColor Green

$workflowCheck = & $python -c @"
import os, sys
root = sys.argv[1]
hits = []
for dp, _, fs in os.walk(root):
    for f in fs:
        if 'nf4' in f and f.endswith('.json'):
            hits.append(os.path.join(dp, f))
print(hits[0] if hits else '')
"@ $distRoot
if (-not $workflowCheck) {
    Write-Host '[ERROR] ComfyUI workflow JSON not found in dist bundle' -ForegroundColor Red
    exit 1
}
Write-Host "[OK] ComfyUI workflow bundled: $workflowCheck" -ForegroundColor Green

# Download WebView2 Bootstrapper if not exists
$webview2Path = Join-Path $PSScriptRoot 'installer_assets\MicrosoftEdgeWebview2Setup.exe'
if (-not (Test-Path $webview2Path)) {
    Write-Host "Downloading Microsoft WebView2 Bootstrapper..." -ForegroundColor Cyan
    try {
        $webview2Dir = Split-Path $webview2Path -Parent
        if (-not (Test-Path $webview2Dir)) {
            New-Item -ItemType Directory -Path $webview2Dir -Force | Out-Null
        }
        
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri "https://go.microsoft.com/fwlink/p/?LinkId=2124703" -OutFile $webview2Path -UseBasicParsing
        
        if (Test-Path $webview2Path) {
            $size = [math]::Round((Get-Item $webview2Path).Length / 1MB, 2)
            Write-Host "[OK] WebView2 Bootstrapper downloaded ($size MB)" -ForegroundColor Green
        } else {
            Write-Host "[WARN] WebView2 download failed, installer will not include WebView2" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "[WARN] WebView2 download failed: $_" -ForegroundColor Yellow
        Write-Host "  Users can manually install WebView2 or use 'start_xiaoboom.bat'" -ForegroundColor Yellow
    }
} else {
    Write-Host "[OK] WebView2 Bootstrapper already exists" -ForegroundColor Gray
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
    Write-Host "`nBuilding Inno Setup installer..." -ForegroundColor Cyan
    & $iscc '.\aiwritex_installer.iss'
    
    if ($LASTEXITCODE -eq 0) {
        $setupFile = Get-ChildItem -Path (Join-Path $PSScriptRoot 'dist\installer') -Filter '*-Setup.exe' -ErrorAction SilentlyContinue |
                    Sort-Object LastWriteTime -Descending |
                    Select-Object -First 1
        if ($setupFile) {
            $size = [math]::Round($setupFile.Length / 1MB, 2)
            Write-Host "`n========================================" -ForegroundColor Green
            Write-Host "[SUCCESS] Installer build completed!" -ForegroundColor Green
            Write-Host "  File: $($setupFile.Name)" -ForegroundColor White
            Write-Host "  Size: $size MB" -ForegroundColor White
            Write-Host "  Path: $($setupFile.FullName)" -ForegroundColor Gray
            Write-Host "========================================" -ForegroundColor Green
        }
    } else {
        Write-Host "`n[ERROR] Inno Setup build failed" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host 'Inno Setup not found. onedir build completed. Install Inno Setup 6 and rerun this script for Setup.exe.'
}
