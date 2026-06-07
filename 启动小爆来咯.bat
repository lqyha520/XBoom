@echo off
setlocal enabledelayedexpansion

title XBoom - Packaged Start

echo ========================================
echo   XBoom packaged app environment check
echo ========================================
echo.

echo [1/2] Checking Microsoft Edge WebView2 Runtime...

set "WEBVIEW2_OK=0"
reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1 && set "WEBVIEW2_OK=1"
reg query "HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1 && set "WEBVIEW2_OK=1"
reg query "HKCU\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1 && set "WEBVIEW2_OK=1"

if "!WEBVIEW2_OK!"=="1" (
    echo [OK] WebView2 is installed.
    goto :check_complete
)

echo [INFO] WebView2 was not detected or may be damaged.
echo Installing WebView2...
echo.

if exist "%~dp0installer_assets\MicrosoftEdgeWebview2Setup.exe" (
    echo Using local installer...
    "%~dp0installer_assets\MicrosoftEdgeWebview2Setup.exe" /silent /install
) else (
    echo Downloading installer from Microsoft...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "& { $url = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'; $out = Join-Path $env:TEMP 'MicrosoftEdgeWebview2Setup.exe'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing; Start-Process -FilePath $out -ArgumentList '/silent /install' -Wait -NoNewWindow; Remove-Item $out -Force -ErrorAction SilentlyContinue }"
)

if !errorlevel! neq 0 (
    echo.
    echo [ERROR] WebView2 installation failed.
    echo Please install it manually:
    echo https://developer.microsoft.com/en-us/microsoft-edge/webview2/
    echo.
    pause
    exit /b 1
)

:check_complete
echo.
echo [2/2] Environment check completed.
echo.

echo Starting XBoom...
set "APP_EXE="
for %%F in ("%~dp0*.exe") do (
    if /I not "%%~nxF"=="MicrosoftEdgeWebview2Setup.exe" (
        set "APP_EXE=%%~fF"
        goto :launch_app
    )
)

:launch_app
if defined APP_EXE (
    start "" "!APP_EXE!"
) else (
    echo [ERROR] App exe was not found. Please check the installation directory.
    pause
    exit /b 1
)

exit /b 0
