@echo off
setlocal enabledelayedexpansion

title XBoom - Start

echo ========================================
echo   XBoom is starting...
echo ========================================
echo.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    python --version >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=python"
    ) else (
        echo [ERROR] Python was not found.
        echo Please run the dependency setup bat first.
        echo You can also run: python scripts\doctor.py
        pause
        exit /b 1
    )
) else (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
)

if not defined AIWRITEX_BROWSER_GUI set "AIWRITEX_BROWSER_GUI=0"
if exist "logs\use_browser_gui.flag" del /f /q "logs\use_browser_gui.flag" >nul 2>&1

REM Desktop mode requires Microsoft Edge WebView2 Runtime.
if "!AIWRITEX_BROWSER_GUI!"=="0" (
    set "WEBVIEW2_OK=0"
    reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1 && set "WEBVIEW2_OK=1"
    reg query "HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1 && set "WEBVIEW2_OK=1"
    reg query "HKCU\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1 && set "WEBVIEW2_OK=1"

    if "!WEBVIEW2_OK!"=="0" (
        echo [INFO] Microsoft Edge WebView2 Runtime was not detected.
        echo Desktop mode may not open. You can use start-browser.bat / the browser startup bat instead.
        choice /C YN /M "Open the WebView2 installer page now"
        if !errorlevel! equ 1 (
            start "" "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
            echo After installation, run this bat again.
            pause
            exit /b 0
        )
    )
)

echo [Python] !PYTHON_EXE!
if "!AIWRITEX_BROWSER_GUI!"=="1" (
    echo [Mode] Browser
) else (
    echo [Mode] Desktop window
)
echo.
echo Starting, please wait...
echo.

"!PYTHON_EXE!" main.py
if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Program exited abnormally. Exit code: !errorlevel!
    echo Suggested diagnosis: "!PYTHON_EXE!" scripts\doctor.py
    pause
)
