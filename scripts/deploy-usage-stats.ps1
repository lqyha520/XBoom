# 部署使用统计接口到宝塔，并初始化 MySQL 库 XBoom
# 用法:
#   1. 复制 scripts\usage-stats.env.example -> scripts\usage-stats.env
#   2. 填写 SSH、MySQL 密码
#   3. powershell -ExecutionPolicy Bypass -File .\scripts\deploy-usage-stats.ps1

param(
    [switch]$SkipDbInit
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$EnvFile = Join-Path $Root 'scripts\usage-stats.env'
if (-not (Test-Path $EnvFile)) {
    Write-Host "请先创建 scripts\usage-stats.env（参考 usage-stats.env.example）" -ForegroundColor Red
    exit 1
}

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
        Set-Variable -Name $matches[1].Trim() -Value $matches[2].Trim() -Scope Script
    }
}

if (-not $SSH_HOST) {
    Write-Host "请在 usage-stats.env 中设置 SSH_HOST" -ForegroundColor Red
    exit 1
}
if (-not $STATS_REMOTE_DIR) {
    $STATS_REMOTE_DIR = '/www/wwwroot/updates.bcxtech.cn/stats'
}
if (-not $STATS_BASE_URL) {
    $STATS_BASE_URL = 'https://updates.bcxtech.cn/stats'
}
if (-not $SSH_USER) { $SSH_USER = 'root' }
if (-not $SSH_PORT) { $SSH_PORT = '22' }
if (-not $MYSQL_DATABASE) { $MYSQL_DATABASE = 'XBoom' }
if (-not $MYSQL_HOST) { $MYSQL_HOST = '127.0.0.1' }
if (-not $MYSQL_PORT) { $MYSQL_PORT = '3306' }
if (-not $MYSQL_USER) { $MYSQL_USER = 'root' }

$Remote = "${SSH_USER}@${SSH_HOST}"
$RemoteDir = $STATS_REMOTE_DIR.TrimEnd('/')
$StatsSrc = Join-Path $Root 'services\usage-stats'
$SchemaFile = Join-Path $StatsSrc 'schema.sql'

function Get-SshBaseArgs {
    $args = @()
    if ($SSH_PORT -and $SSH_PORT -ne '22') { $args += '-p', $SSH_PORT }
    $keyCandidates = @()
    if ($SSH_KEY_PATH) { $keyCandidates += $SSH_KEY_PATH }
    $keyCandidates += (Join-Path $Root 'xiaobao.pem')
    foreach ($k in $keyCandidates) {
        if ($k -and (Test-Path $k)) {
            $args += '-i', $k, '-o', 'StrictHostKeyChecking=accept-new'
            break
        }
    }
    return $args
}

$sshArgs = Get-SshBaseArgs
$scpArgs = @()
if ($SSH_PORT -and $SSH_PORT -ne '22') { $scpArgs += '-P', $SSH_PORT }
foreach ($k in @($SSH_KEY_PATH, (Join-Path $Root 'xiaobao.pem'))) {
    if ($k -and (Test-Path $k)) {
        $scpArgs += '-i', $k, '-o', 'StrictHostKeyChecking=accept-new'
        break
    }
}

# 本地生成 config.php（不上传 example）
$configPhp = Join-Path $StatsSrc 'config.php'
$dbPassEsc = ($MYSQL_PASSWORD -replace '\\', '\\\\' -replace "'", "\\'")
$dbUserEsc = ($MYSQL_USER -replace "'", "\\'")
$dbHostEsc = ($MYSQL_HOST -replace "'", "\\'")
@"
<?php
return [
    'db_host' => '$dbHostEsc',
    'db_port' => $MYSQL_PORT,
    'db_name' => '$MYSQL_DATABASE',
    'db_user' => '$dbUserEsc',
    'db_pass' => '$dbPassEsc',
    'report_token' => '',
    'rate_limit_per_hour' => 30,
];
"@ | Set-Content -Path $configPhp -Encoding UTF8
Write-Host "已生成 config.php（仅用于上传）"

Write-Host "目标: ${Remote}:${RemoteDir}"
Write-Host "上报地址: $STATS_BASE_URL/report.php"
Write-Host ""

& ssh.exe @sshArgs $Remote "mkdir -p '$RemoteDir'"

Write-Host "上传 report.php、menu_access_check.php、config.php ..."
& scp.exe @scpArgs (Join-Path $StatsSrc 'report.php') "${Remote}:${RemoteDir}/report.php"
& scp.exe @scpArgs (Join-Path $StatsSrc 'menu_access_check.php') "${Remote}:${RemoteDir}/menu_access_check.php"
& scp.exe @scpArgs (Join-Path $StatsSrc 'config.php') "${Remote}:${RemoteDir}/config.php"

if (-not $SkipDbInit) {
    if (-not $MYSQL_PASSWORD) {
        Write-Host "未设置 MYSQL_PASSWORD，跳过远程建库。请在宝塔手动导入: services\usage-stats\schema.sql" -ForegroundColor Yellow
    } else {
        Write-Host "初始化 MySQL 库 $MYSQL_DATABASE ..."
        $schemaRemote = '/tmp/xboom_schema.sql'
        & scp.exe @scpArgs $SchemaFile "${Remote}:${schemaRemote}"
        $mysqlCmd = "mysql -h'$MYSQL_HOST' -P'$MYSQL_PORT' -u'$MYSQL_USER' -p'$MYSQL_PASSWORD' < '$schemaRemote' && rm -f '$schemaRemote'"
        & ssh.exe @sshArgs $Remote $mysqlCmd
        if ($LASTEXITCODE -eq 0) {
            Write-Host "数据库表已创建/更新。" -ForegroundColor Green
        } else {
            Write-Host "远程 mysql 执行失败。请在宝塔 → 数据库 → 导入 schema.sql" -ForegroundColor Yellow
        }
    }
}

Write-Host ""
Write-Host "部署完成。验证:" -ForegroundColor Green
Write-Host "  浏览器打开站点目录可访问（需 PHP）"
Write-Host "  客户端默认上报: $STATS_BASE_URL/report.php"
Write-Host "  宝塔 → 数据库 → XBoom → usage_users / usage_visits 查看数据"
