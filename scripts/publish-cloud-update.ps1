# 生成 version-policy.json（含网盘/OSS 直链），供上传到 Gitee 或任意静态托管
# 用法:
#   1. 复制 cloud-update.env.example -> cloud-update.env，填 MANIFEST_URL 的「目录」对应的 INSTALLER_URL
#   2. 先 build 安装包，把 AIWriteX-Setup.exe 上传到你的网盘/OSS，复制直链到 INSTALLER_URL
#   3. powershell -ExecutionPolicy Bypass -File .\scripts\publish-cloud-update.ps1
#   4. 将生成的 version-policy.cloud.json 上传到 Gitee（与 MANIFEST_URL 路径一致）

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$EnvFile = Join-Path $Root 'scripts\cloud-update.env'
if (-not (Test-Path $EnvFile)) {
    Write-Host "请先创建 scripts\cloud-update.env（参考 cloud-update.env.example）" -ForegroundColor Red
    exit 1
}

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
        Set-Variable -Name $matches[1].Trim() -Value $matches[2].Trim() -Scope Script
    }
}

if (-not $INSTALLER_URL) {
    Write-Host "请填写 INSTALLER_URL（安装包直链）" -ForegroundColor Red
    exit 1
}

$Version = (python -c "from src.ai_write_x.version import get_version; print(get_version())").Trim()
$Out = Join-Path $Root 'version-policy.cloud.json'

$Policy = [ordered]@{
    latest_version          = $Version
    min_supported_version   = '23.0.8'
    auto_update_on_startup  = $true
    auto_update_silent      = $true
    download_url            = $INSTALLER_URL
    release_notes           = "AIWriteX v$Version"
    published_at            = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
}

$json = $Policy | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($Out, $json + "`n", [System.Text.UTF8Encoding]::new($false))

Write-Host "已生成: $Out" -ForegroundColor Green
Write-Host ""
Write-Host "下一步:" -ForegroundColor Cyan
Write-Host "  1. 上传 dist\installer\AIWriteX-Setup.exe 到网盘/OSS，确认 INSTALLER_URL 可浏览器直接下载"
Write-Host "  2. 把 $Out 上传到 Gitee/仓库，得到 MANIFEST_URL 直链"
Write-Host "  3. 在 config.yaml 的 update 段设置:"
if ($MANIFEST_URL) {
    Write-Host "       manifest_url: `"$MANIFEST_URL`""
} else {
    Write-Host "       manifest_url: `"https://gitee.com/你的仓库/raw/master/version-policy.json`""
}
Write-Host "     （manifest 里已含 download_url，无需再填 manual_download_url）"
