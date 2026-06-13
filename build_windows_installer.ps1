param(
    [switch]$VerifyInstaller
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

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
if (Test-Path '.\dist') {
    Remove-Item '.\dist' -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host 'Exporting factory config (no personal settings)...' -ForegroundColor Cyan
& $python '.\scripts\export_factory_config_for_build.py'
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host 'Validating PyInstaller spec syntax...' -ForegroundColor Cyan
& $python -m py_compile '.\aiwritex_windows.spec'
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERROR] aiwritex_windows.spec has a syntax/encoding error. Fix it before building.' -ForegroundColor Red
    exit $LASTEXITCODE
}

& $python -m PyInstaller '.\aiwritex_windows.spec' --noconfirm
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

# Self-heal: normalize a possibly mojibake-named PyInstaller onedir to the expected name.
& $python '.\scripts\normalize_dist_dir.py'
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERROR] Failed to normalize dist output directory name.' -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host 'Analyzing PyInstaller warnings...' -ForegroundColor Cyan
& $python '.\scripts\analyze_pyinstaller_warnings.py'
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host 'Running dist bundle validation...' -ForegroundColor Cyan
& $python '.\scripts\check_dist_bundle.py' --skip-installer-size
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

# Download WebView2 Bootstrapper if not exists
$webview2Path = Join-Path $PSScriptRoot 'installer_assets\MicrosoftEdgeWebview2Setup.exe'
if (-not (Test-Path $webview2Path)) {
    Write-Host 'Downloading Microsoft WebView2 Bootstrapper...' -ForegroundColor Cyan
    try {
        $webview2Dir = Split-Path $webview2Path -Parent
        if (-not (Test-Path $webview2Dir)) {
            New-Item -ItemType Directory -Path $webview2Dir -Force | Out-Null
        }

        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $webview2Path -UseBasicParsing

        if (Test-Path $webview2Path) {
            $size = [math]::Round((Get-Item $webview2Path).Length / 1MB, 2)
            Write-Host "[OK] WebView2 Bootstrapper downloaded ($size MB)" -ForegroundColor Green
        } else {
            Write-Host '[WARN] WebView2 download failed, installer will not include WebView2' -ForegroundColor Yellow
        }
    } catch {
        Write-Host "[WARN] WebView2 download failed: $_" -ForegroundColor Yellow
        Write-Host '  Users can manually install WebView2 or use the browser startup bat.' -ForegroundColor Yellow
    }
} else {
    Write-Host '[OK] WebView2 Bootstrapper already exists' -ForegroundColor Gray
}

$isccCandidates = @(
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    'C:\Program Files\Inno Setup 6\ISCC.exe',
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramData 'chocolatey\bin\ISCC.exe')
)

# Inno Setup records its install dir in the registry; use it as an extra candidate.
foreach ($regPath in @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1'
)) {
    try {
        $loc = (Get-ItemProperty -Path $regPath -ErrorAction Stop).InstallLocation
        if ($loc) { $isccCandidates += (Join-Path $loc 'ISCC.exe') }
    } catch {}
}

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
        $setupFile = Get-ChildItem -Path (Join-Path $PSScriptRoot 'dist\installer') -Filter '*-Setup-v*.exe' -ErrorAction SilentlyContinue |
                    Sort-Object LastWriteTime -Descending |
                    Select-Object -First 1
        if ($setupFile) {
            $size = [math]::Round($setupFile.Length / 1MB, 2)
            Write-Host "`n========================================" -ForegroundColor Green
            Write-Host '[SUCCESS] Installer build completed!' -ForegroundColor Green
            Write-Host "  File: $($setupFile.Name)" -ForegroundColor White
            Write-Host "  Size: $size MB" -ForegroundColor White
            Write-Host "  Path: $($setupFile.FullName)" -ForegroundColor Gray
            Write-Host '========================================' -ForegroundColor Green

            Write-Host "`nRunning installer size validation..." -ForegroundColor Cyan
            & $python '.\scripts\check_dist_bundle.py'
            if ($LASTEXITCODE -ne 0) {
                exit $LASTEXITCODE
            }

            if ($VerifyInstaller -or $env:XBoom_VERIFY_INSTALLER -eq '1') {
                Write-Host "`nVerifying installer install/uninstall behavior..." -ForegroundColor Cyan
                & $python '.\scripts\verify_installer.py' --installer $setupFile.FullName
                if ($LASTEXITCODE -ne 0) {
                    exit $LASTEXITCODE
                }
            }
        }
    } else {
        Write-Host "`n[ERROR] Inno Setup build failed" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host 'Inno Setup not found. onedir build completed. Install Inno Setup 6 and rerun this script for Setup.exe.' -ForegroundColor Yellow
    Write-Host 'Searched the following ISCC.exe locations:' -ForegroundColor Yellow
    $isccCandidates | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
}
