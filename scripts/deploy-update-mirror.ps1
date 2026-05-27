# 将安装包与 version-policy.json 自动上传到宝塔 / 国内镜像服务器
# 用法:
#   1. 复制 scripts\update-mirror.env.example -> scripts\update-mirror.env
#   2. 填写 MIRROR_BASE_URL、SSH_HOST、REMOTE_DIR
#   3. 本机先能 ssh 登录: ssh root@你的IP
#   4. powershell -ExecutionPolicy Bypass -File .\scripts\deploy-update-mirror.ps1
# 或由 publish-gitee-release.ps1 在发版结束时自动调用

param(
    [string]$PolicyFile = '',
    [string]$SetupFile = ''
)

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

if (-not $SSH_HOST) {
    Write-Host "请在 update-mirror.env 中设置 SSH_HOST（服务器公网 IP）" -ForegroundColor Red
    exit 1
}

$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }
$Version = (& $python -c "from src.ai_write_x.version import get_version; print(get_version())").Trim()
$InstallerName = (& $python -c "import sys; sys.path.insert(0, r'$Root'); from src.ai_write_x.branding.install import INSTALLER_NAME; print(INSTALLER_NAME)").Trim()

if (-not $SetupFile) {
    $SetupItem = Get-ChildItem -Path (Join-Path $Root 'dist\installer') -Filter '*-Setup.exe' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $SetupItem) {
        Write-Host "未找到安装包，请先运行: .\build_windows_installer.ps1" -ForegroundColor Red
        exit 1
    }
    $SetupFile = $SetupItem.FullName
}

if (-not $PolicyFile) {
    $PolicyFile = Join-Path $Root 'version-policy.json'
    if (-not (Test-Path $PolicyFile)) {
        $Base = $MIRROR_BASE_URL.TrimEnd('/')
        $Policy = @{
            latest_version = $Version
            min_supported_version = '1.0.0'
            auto_update_on_startup = $true
            auto_update_silent = $true
            download_url = "$Base/$InstallerName"
            release_notes = "小爆来咯 v$Version"
            published_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        }
        $Policy | ConvertTo-Json -Depth 5 | Set-Content -Path $PolicyFile -Encoding UTF8
    }
}

if (-not (Test-Path $SetupFile)) {
    Write-Host "安装包不存在: $SetupFile" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $PolicyFile)) {
    Write-Host "策略文件不存在: $PolicyFile" -ForegroundColor Red
    exit 1
}

if (-not $REMOTE_DIR) {
    $REMOTE_DIR = '/www/wwwroot/updates'
}
if (-not $SSH_USER) {
    $SSH_USER = 'root'
}
if (-not $SSH_PORT) {
    $SSH_PORT = '22'
}

$Remote = "${SSH_USER}@${SSH_HOST}"
$RemoteDir = $REMOTE_DIR.TrimEnd('/')

function Get-SshBaseArgs {
    $args = @()
    if ($SSH_PORT -and $SSH_PORT -ne '22') {
        $args += '-p', $SSH_PORT
    }
    if ($SSH_KEY_PATH -and (Test-Path $SSH_KEY_PATH)) {
        $args += '-i', $SSH_KEY_PATH
        $args += '-o', 'StrictHostKeyChecking=accept-new'
    }
    return $args
}

function Get-ScpBaseArgs {
    $args = @()
    if ($SSH_PORT -and $SSH_PORT -ne '22') {
        $args += '-P', $SSH_PORT
    }
    if ($SSH_KEY_PATH -and (Test-Path $SSH_KEY_PATH)) {
        $args += '-i', $SSH_KEY_PATH
        $args += '-o', 'StrictHostKeyChecking=accept-new'
    }
    return $args
}

$pyUpload = Join-Path $Root 'scripts\ssh-upload-mirror.py'
if ($env:SSH_PASSWORD -and (Test-Path $pyUpload)) {
    Write-Host "使用 SSH_PASSWORD + Python 上传..."
    & (Join-Path $Root '.venv\Scripts\python.exe') $pyUpload -PolicyFile $PolicyFile -SetupFile $SetupFile
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    exit 0
}

$sshCmd = Get-Command ssh.exe -ErrorAction SilentlyContinue
$scpCmd = Get-Command scp.exe -ErrorAction SilentlyContinue
if (-not $sshCmd -or -not $scpCmd) {
    Write-Host "未找到 OpenSSH（ssh/scp）。可设置环境变量 SSH_PASSWORD 使用 Python 上传，或启用 OpenSSH 客户端。" -ForegroundColor Red
    exit 1
}

Write-Host "版本: v$Version"
Write-Host "目标: ${Remote}:${RemoteDir}"
Write-Host "安装包: $SetupFile ($([math]::Round((Get-Item $SetupFile).Length / 1MB, 1)) MB)"
Write-Host "策略: $PolicyFile"
Write-Host "用户下载: $($MIRROR_BASE_URL.TrimEnd('/'))/$InstallerName"
Write-Host ""

$sshArgs = Get-SshBaseArgs
$scpArgs = Get-ScpBaseArgs

Write-Host "创建远程目录..."
& ssh.exe @sshArgs $Remote "mkdir -p '$RemoteDir'"

Write-Host "上传 version-policy.json ..."
& scp.exe @scpArgs $PolicyFile "${Remote}:${RemoteDir}/version-policy.json"

Write-Host "上传安装包（约 1～3 分钟，视带宽而定）..."
& scp.exe @scpArgs $SetupFile "${Remote}:${RemoteDir}/$InstallerName"

Write-Host ""
Write-Host "上传完成。请在浏览器验证:" -ForegroundColor Green
Write-Host "  $($MIRROR_BASE_URL.TrimEnd('/'))/version-policy.json"
Write-Host "  $($MIRROR_BASE_URL.TrimEnd('/'))/$InstallerName"
