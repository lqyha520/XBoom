@echo off

chcp 65001 >nul

title 修复本程序 WebView2 缓存

echo ========================================

echo   仅修复「小爆来咯」本地缓存

echo ========================================

echo.

echo 注意：不会结束系统里其他程序的 WebView2 进程。

echo 若微信/钉钉等也白屏，请运行「恢复系统WebView2.bat」。

echo.



cd /d "%~dp0"



if exist "logs\use_browser_gui.flag" del /f /q "logs\use_browser_gui.flag"

if exist "pywebview" rd /s /q "pywebview" 2>nul



echo 将打开 WebView2 运行时安装/修复页（可点「修复」或重装）...

start "" "https://go.microsoft.com/fwlink/p/?LinkId=2124703"

echo 完成后关闭所有白屏程序，再逐个重新打开。

pause

