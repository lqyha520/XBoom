@echo off

setlocal enabledelayedexpansion

title 小爆来咯 - 启动

echo ========================================

echo   小爆来咯 启动中...

echo ========================================

echo.



cd /d "%~dp0"



if not exist ".venv\Scripts\python.exe" (

    python --version >nul 2>&1

    if !errorlevel! equ 0 (

        set "PYTHON_EXE=python"

    ) else (

        echo [错误] 未找到 Python，请先运行 setup.bat 安装环境。

        pause

        exit /b 1

    )

) else (

    set "PYTHON_EXE=.venv\Scripts\python.exe"

)



if not defined AIWRITEX_BROWSER_GUI set "AIWRITEX_BROWSER_GUI=0"

if exist "logs\use_browser_gui.flag" del /f /q "logs\use_browser_gui.flag"



REM 桌面模式：新电脑若未装 WebView2，自动提示一次

if "!AIWRITEX_BROWSER_GUI!"=="0" (

    set "WEBVIEW2_OK=0"

    reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1 && set "WEBVIEW2_OK=1"

    if "!WEBVIEW2_OK!"=="0" (

        reg query "HKCU\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1 && set "WEBVIEW2_OK=1"

    )

    if "!WEBVIEW2_OK!"=="0" (

        echo [提示] 本机未检测到 WebView2 运行时，桌面窗口可能无法打开。

        choice /C YN /M "是否现在安装 WebView2"

        if !errorlevel! equ 1 (

            start "" "https://go.microsoft.com/fwlink/p/?LinkId=2124703"

            echo 安装完成后请重新双击「启动.bat」。

            pause

            exit /b 0

        )

    )

)



echo [Python] !PYTHON_EXE!

if "!AIWRITEX_BROWSER_GUI!"=="1" (

    echo [模式] 系统浏览器

) else (

    echo [模式] 桌面窗口

)

echo.

echo 正在启动，请稍候...

echo.



"!PYTHON_EXE!" main.py

if !errorlevel! neq 0 (

    echo.

    echo [错误] 程序异常退出，代码: !errorlevel!

    pause

)

