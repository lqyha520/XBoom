@echo off

chcp 65001 >nul

title 恢复系统 WebView2（多程序白屏时用）

echo ========================================

echo   恢复系统 WebView2（其他软件也白屏时）

echo ========================================

echo.

echo 原因说明：此前启动脚本曾误结束全部 WebView2 进程，

echo 可能导致微信、钉钉、Cursor 等界面变白。

echo.

echo 请按顺序操作：

echo   1. 保存工作，关闭所有白屏程序

echo   2. 重启电脑（推荐，最快恢复）

echo   3. 重启后打开下方链接，重装/修复 WebView2 运行时

echo   4. 再逐个重新打开需要的软件

echo.

echo 本程序请优先使用「启动-浏览器.bat」，避免再次影响系统 WebView2。

echo.

pause

start "" "https://go.microsoft.com/fwlink/p/?LinkId=2124703"

echo.

echo 也可在：设置 - 应用 - 已安装应用 - 搜索「WebView2」- 修改/修复

pause

