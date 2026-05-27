# 发布当前版本到 GitHub Release（供自动更新拉取）
# 用法：先 gh auth login，再在本目录执行：
#   powershell -ExecutionPolicy Bypass -File .\scripts\publish-release.ps1

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Version = (python -c "from src.ai_write_x.version import get_version; print(get_version())").Trim()
$Tag = "v$Version"
$SetupItem = Get-ChildItem -Path (Join-Path $Root 'dist\installer') -Filter '*-Setup.exe' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$Setup = if ($SetupItem) { $SetupItem.FullName } else { $null }
$Policy = Join-Path $Root "version-policy.json"

if (-not (Test-Path $Setup)) {
    Write-Host "未找到安装包，请先运行: .\build_windows_installer.ps1" -ForegroundColor Red
    exit 1
}

gh auth status | Out-Null

Write-Host "推送代码到 origin/main ..."
git push origin main

Write-Host "创建 Release $Tag ..."
$uploadOk = $false
try {
    gh release upload $Tag $Setup $Policy --clobber 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $uploadOk = $true }
} catch {}

if (-not $uploadOk) {
    gh release create $Tag $Setup $Policy `
        --title "小爆来咯 $Tag" `
        --notes-file $Policy `
        --latest
}

Write-Host "完成。Release: https://github.com/lqyha520/AIWriteX-main/releases/tag/$Tag" -ForegroundColor Green
