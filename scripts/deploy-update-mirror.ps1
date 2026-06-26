# 将安装包与 version-policy.json 自动上传到宝塔 / 国内镜像服务器
# 用法:
#   1. 复制 scripts\update-mirror.env.example -> scripts\update-mirror.env
#   2. 填写 MIRROR_BASE_URL、SSH_HOST、REMOTE_DIR
#   3. 本机先能 ssh 登录: ssh root@你的IP
#   4. powershell -ExecutionPolicy Bypass -File .\scripts\deploy-update-mirror.ps1
# 或由 publish-gitee-release.ps1 在发版结束时自动调用

param(
    [string]$PolicyFile = '',
    [string]$SetupFile = '',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$Utf8Encoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $Utf8Encoding
$OutputEncoding = $Utf8Encoding
$env:PYTHONIOENCODING = 'utf-8'

$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$Root = Split-Path -Parent $ScriptDir
Set-Location $Root

$EnvFile = Join-Path $Root 'scripts\update-mirror.env'
if (-not (Test-Path $EnvFile)) {
    Write-Host "请先创建 scripts\update-mirror.env（参考 update-mirror.env.example）" -ForegroundColor Red
    exit 1
}

function Read-MirrorEnv {
    param([string]$Path)

    $config = @{}
    foreach ($rawLine in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#')) {
            continue
        }

        $separator = $line.IndexOf('=')
        if ($separator -lt 1) {
            continue
        }

        $key = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $config[$key] = $value
    }

    return $config
}

function Require-MirrorValue {
    param(
        [hashtable]$Config,
        [string]$Name,
        [string]$Message
    )

    $value = $Config[$Name]
    if ([string]::IsNullOrWhiteSpace($value)) {
        Write-Host $Message -ForegroundColor Red
        exit 1
    }
    return $value.Trim()
}

$MirrorConfig = Read-MirrorEnv -Path $EnvFile

$MIRROR_BASE_URL = Require-MirrorValue -Config $MirrorConfig -Name 'MIRROR_BASE_URL' -Message '请在 update-mirror.env 中设置 MIRROR_BASE_URL'
$SSH_HOST = Require-MirrorValue -Config $MirrorConfig -Name 'SSH_HOST' -Message '请在 update-mirror.env 中设置 SSH_HOST（服务器公网 IP）'
$SSH_USER = if ([string]::IsNullOrWhiteSpace($MirrorConfig['SSH_USER'])) { 'root' } else { $MirrorConfig['SSH_USER'].Trim() }
$SSH_PORT = if ([string]::IsNullOrWhiteSpace($MirrorConfig['SSH_PORT'])) { '22' } else { $MirrorConfig['SSH_PORT'].Trim() }
$REMOTE_DIR = if ([string]::IsNullOrWhiteSpace($MirrorConfig['REMOTE_DIR'])) { '/www/wwwroot/updates.bcxtech.cn/updates' } else { $MirrorConfig['REMOTE_DIR'].Trim() }
$SSH_KEY_PATH = if ([string]::IsNullOrWhiteSpace($MirrorConfig['SSH_KEY_PATH'])) { '.local_secrets\xiaobao.pem' } else { $MirrorConfig['SSH_KEY_PATH'].Trim() }
if ($SSH_KEY_PATH -and -not [System.IO.Path]::IsPathRooted($SSH_KEY_PATH)) {
    $SSH_KEY_PATH = Join-Path $Root $SSH_KEY_PATH
}

$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }
$Version = (& $python -c "from src.ai_write_x.version import get_version; print(get_version())").Trim()
$InstallerName = (& $python -c "import sys; sys.path.insert(0, r'$Root'); from src.ai_write_x.branding.install import INSTALLER_NAME; print(INSTALLER_NAME)").Trim()

if (-not $SetupFile) {
    $ExpectedSetupFile = Join-Path (Join-Path $Root 'dist\installer') $InstallerName
    if (Test-Path -LiteralPath $ExpectedSetupFile) {
        $SetupFile = $ExpectedSetupFile
    } else {
        $SetupItem = Get-ChildItem -Path (Join-Path $Root 'dist\installer') -Filter '*-Setup-v*.exe' -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($SetupItem) {
            $SetupFile = $SetupItem.FullName
        }
    }
    if (-not $SetupFile) {
        Write-Host "未找到安装包，请先运行: .\build_windows_installer.ps1" -ForegroundColor Red
        exit 1
    }
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

if (-not (Test-Path -LiteralPath $SetupFile)) {
    Write-Host "安装包不存在: $SetupFile" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -LiteralPath $PolicyFile)) {
    Write-Host "策略文件不存在: $PolicyFile" -ForegroundColor Red
    exit 1
}

$SetupFile = (Resolve-Path -LiteralPath $SetupFile).Path
$PolicyFile = (Resolve-Path -LiteralPath $PolicyFile).Path

$Remote = "${SSH_USER}@${SSH_HOST}"
$RemoteDir = $REMOTE_DIR.TrimEnd('/')
$MirrorBaseUrl = $MIRROR_BASE_URL.TrimEnd('/')

function Get-SshBaseArgs {
    $args = @()
    if ($SSH_PORT -and $SSH_PORT -ne '22') {
        $args += '-p', $SSH_PORT
    }
    if ($SSH_KEY_PATH -and (Test-Path -LiteralPath $SSH_KEY_PATH)) {
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
    if ($SSH_KEY_PATH -and (Test-Path -LiteralPath $SSH_KEY_PATH)) {
        $args += '-i', $SSH_KEY_PATH
        $args += '-o', 'StrictHostKeyChecking=accept-new'
    }
    return $args
}

function Invoke-CheckedNative {
    param(
        [string]$Command,
        [string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE"
    }
}

try {
    $Policy = Get-Content -LiteralPath $PolicyFile -Encoding UTF8 | ConvertFrom-Json
    if ($Policy.latest_version -and $Policy.latest_version -ne $Version) {
        Write-Host "version-policy.json 版本($($Policy.latest_version))与当前版本(v$Version)不一致" -ForegroundColor Red
        exit 1
    }
    if ($Policy.sha256) {
        $SetupHash = (Get-FileHash -LiteralPath $SetupFile -Algorithm SHA256).Hash.ToLower()
        if ($Policy.sha256.ToLower() -ne $SetupHash) {
            Write-Host "version-policy.json sha256 与安装包不一致" -ForegroundColor Red
            Write-Host "  policy: $($Policy.sha256)" -ForegroundColor Red
            Write-Host "  setup : $SetupHash" -ForegroundColor Red
            exit 1
        }
    }
} catch {
    Write-Host "无法校验 version-policy.json: $_" -ForegroundColor Red
    exit 1
}

$pyUpload = Join-Path $Root 'scripts\ssh-upload-mirror.py'
if ($env:SSH_PASSWORD -and (Test-Path $pyUpload)) {
    Write-Host "使用 SSH_PASSWORD + Python 上传..."
    if ($DryRun) {
        Write-Host "Dry run: skip Python upload."
        exit 0
    }
    Invoke-CheckedNative -Command $python -Arguments @($pyUpload, '-PolicyFile', $PolicyFile, '-SetupFile', $SetupFile)
    exit 0
}

$sshCmd = Get-Command ssh.exe -ErrorAction SilentlyContinue
$scpCmd = Get-Command scp.exe -ErrorAction SilentlyContinue
if (-not $sshCmd -or -not $scpCmd) {
    Write-Host "OpenSSH not found (ssh/scp). Set SSH_PASSWORD for Python upload or enable OpenSSH client." -ForegroundColor Red
    exit 1
}

Write-Host "Version: v$Version"
Write-Host "Target: ${Remote}:${RemoteDir}"
$setupSizeMb = [math]::Round((Get-Item $SetupFile).Length / 1MB, 1)
Write-Host ("Installer: {0} ({1} MB)" -f $SetupFile, $setupSizeMb)
Write-Host "Policy: $PolicyFile"
Write-Host "Download URL: $MirrorBaseUrl/$InstallerName"
Write-Host ""

$sshArgs = Get-SshBaseArgs
$scpArgs = Get-ScpBaseArgs

if ($DryRun) {
    Write-Host "Dry run: upload skipped." -ForegroundColor Yellow
    exit 0
}

Write-Host "Create remote dir..."
Invoke-CheckedNative -Command 'ssh.exe' -Arguments ($sshArgs + @($Remote, "mkdir -p '$RemoteDir'"))

Write-Host "Upload version-policy.json ..."
Invoke-CheckedNative -Command 'scp.exe' -Arguments ($scpArgs + @($PolicyFile, "${Remote}:${RemoteDir}/version-policy.json"))

Write-Host "Upload installer (about 1-3 minutes)..."
Invoke-CheckedNative -Command 'scp.exe' -Arguments ($scpArgs + @($SetupFile, "${Remote}:${RemoteDir}/$InstallerName"))

Write-Host ""
Write-Host "Upload completed. Verify in browser:" -ForegroundColor Green
Write-Host "  $MirrorBaseUrl/version-policy.json"
Write-Host "  $MirrorBaseUrl/$InstallerName"

