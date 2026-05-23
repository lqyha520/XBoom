# 将安装包与 version-policy.json 部署到国内镜像服务器
# 用法:
#   1. 复制 scripts\update-mirror.env.example 为 scripts\update-mirror.env 并填写
#   2. powershell -ExecutionPolicy Bypass -File .\scripts\deploy-update-mirror.ps1

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$EnvFile = Join-Path $Root 'scripts\update-mirror.env'
if (-not (Test-Path $EnvFile)) {
    Write-Host "请先创建 scripts\update-mirror.env（参考 update-mirror.env.example）" -ForegroundColor Red
    exit 1
}

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
        Set-Variable -Name $matches[1].Trim() -Value $matches[2].Trim() -Scope Script
    }
}

if (-not $MIRROR_BASE_URL) {
    Write-Host "请在 update-mirror.env 中设置 MIRROR_BASE_URL" -ForegroundColor Red
    exit 1
}

$Version = (python -c "from src.ai_write_x.version import get_version; print(get_version())").Trim()
$Setup = Join-Path $Root "dist\installer\AIWriteX-Setup.exe"
if (-not (Test-Path $Setup)) {
    Write-Host "未找到安装包，请先运行: .\build_windows_installer.ps1" -ForegroundColor Red
    exit 1
}

$Base = $MIRROR_BASE_URL.TrimEnd('/')
$DownloadUrl = "$Base/AIWriteX-Setup.exe"
$PolicyPath = Join-Path $Root 'version-policy.mirror.json'

$Policy = @{
    latest_version = $Version
    min_supported_version = '23.0.8'
    auto_update_on_startup = $true
    auto_update_silent = $true
    download_url = $DownloadUrl
    release_notes = "AIWriteX v$Version（国内镜像）"
    published_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
}
$Policy | ConvertTo-Json -Depth 5 | Set-Content -Path $PolicyPath -Encoding UTF8

Write-Host "版本: v$Version"
Write-Host "策略: $PolicyPath"
Write-Host "安装包直链: $DownloadUrl"

if ($SSH_HOST) {
    if (-not $REMOTE_DIR) { $REMOTE_DIR = '/var/www/aiwritex-updates' }
    $Remote = "${SSH_USER}@${SSH_HOST}"
    $PortArg = if ($SSH_PORT -and $SSH_PORT -ne '22') { "-P $SSH_PORT" } else { '' }

    Write-Host "上传到 $Remote:$REMOTE_DIR ..."
    ssh $PortArg.Split(' ') $Remote "mkdir -p $REMOTE_DIR"
    scp $PortArg.Split(' ') $Setup "${Remote}:${REMOTE_DIR}/AIWriteX-Setup.exe"
    scp $PortArg.Split(' ') $PolicyPath "${Remote}:${REMOTE_DIR}/version-policy.json"
    Write-Host "上传完成。" -ForegroundColor Green
} else {
    Write-Host "未配置 SSH，请手动上传以下文件到服务器 $Base 对应目录:" -ForegroundColor Yellow
    Write-Host "  $Setup  ->  AIWriteX-Setup.exe"
    Write-Host "  $PolicyPath  ->  version-policy.json"
}

Write-Host ""
Write-Host "请在 config.yaml 的 update 段加入（或发新版安装包写入默认配置）:" -ForegroundColor Cyan
Write-Host "  update_mirror_base: `"$Base`""
