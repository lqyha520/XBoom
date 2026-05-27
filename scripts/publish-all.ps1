# 一键：打包 + 发布 Gitee/GitHub + 上传腾讯云宝塔镜像
# 用法:
#   1. 配置 scripts\gitee-release.env
#   2. 配置 scripts\update-mirror.env（MIRROR_BASE_URL、SSH_HOST、REMOTE_DIR）
#   3. powershell -ExecutionPolicy Bypass -File .\scripts\publish-all.ps1
#   跳过打包: ...\publish-all.ps1 -SkipBuild

param(
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not $SkipBuild) {
    Write-Host "=== 1/2 打包 Windows 安装包 ===" -ForegroundColor Cyan
    & powershell.exe -ExecutionPolicy Bypass -File (Join-Path $Root 'build_windows_installer.ps1')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host ""
Write-Host "=== 2/2 发布并上传 ===" -ForegroundColor Cyan
& powershell.exe -ExecutionPolicy Bypass -File (Join-Path $Root 'scripts\publish-gitee-release.ps1')
exit $LASTEXITCODE
