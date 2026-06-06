@echo off
chcp 65001 >nul 2>&1
title 小爆来咯 - 环境检查

echo ========================================
echo   小爆来咯 - 运行环境检查
echo ========================================
echo.

:: 检查 WebView2
echo [1/2] 检查 Microsoft WebView2 运行时...

reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3B927B189}" /v pv >nul 2>&1
if %errorlevel% equ 0 (
    echo ✓ WebView2 已安装
    goto :check_complete
)

reg query "HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3B927B189}" /v pv >nul 2>&1
if %errorlevel% equ 0 (
    echo ✓ WebView2 已安装
    goto :check_complete
)

echo ✗ WebView2 未安装或已损坏
echo.
echo 正在下载并安装 WebView2...
echo.

:: 检查是否已有安装程序
if exist "%~dp0installer_assets\MicrosoftEdgeWebview2Setup.exe" (
    echo 使用本地安装程序...
    "%~dp0installer_assets\MicrosoftEdgeWebview2Setup.exe" /silent /install
) else (
    echo 正在从微软服务器下载（约 2MB）...
    
    :: 使用 PowerShell 下载
    powershell -Command "& {
        $url = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'
        $out = \"$env:TEMP\MicrosoftEdgeWebview2Setup.exe\"
        Write-Host '正在下载 WebView2 安装程序...'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing
        Write-Host '正在安装...'
        Start-Process -FilePath $out -ArgumentList '/silent /install' -Wait -NoNewWindow
        Remove-Item $out -Force -ErrorAction SilentlyContinue
    }"
)

if %errorlevel% neq 0 (
    echo.
    echo ✗ WebView2 安装失败！
    echo 请手动访问以下链接安装：
    echo https://developer.microsoft.com/en-us/microsoft-edge/webview2/
    echo.
    pause
    exit /b 1
)

:check_complete
echo.
echo [2/2] 环境检查完成 ✓
echo.

:: 启动主程序
echo 正在启动 小爆来咯...
start "" "%~dp0XBoom.exe"

exit /b 0
