# 发布到 Gitee Release（安装包 + version-policy.json）
# 用法:
#   1. 在 Gitee 创建与 GitHub 同名仓库（或改 gitee-release.env）
#   2. 复制 gitee-release.env.example -> gitee-release.env，填写 GITEE_TOKEN
#   3. 先 build: .\build_windows_installer.ps1
#   4. powershell -ExecutionPolicy Bypass -File .\scripts\publish-gitee-release.ps1

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$EnvFile = Join-Path $Root 'scripts\gitee-release.env'
if (-not (Test-Path $EnvFile)) {
    Write-Host "请先创建 scripts\gitee-release.env" -ForegroundColor Red
    exit 1
}
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
        Set-Variable -Name $matches[1].Trim() -Value $matches[2].Trim() -Scope Script
    }
}
if (-not $GITEE_TOKEN) {
    Write-Host "请填写 GITEE_TOKEN" -ForegroundColor Red
    exit 1
}

$Owner = if ($GITEE_OWNER) { $GITEE_OWNER } else { 'lqyha520' }
$Repo = if ($GITEE_REPO) { $GITEE_REPO } else { 'AIWriteX-main' }
$Branch = if ($GITEE_BRANCH) { $GITEE_BRANCH } else { 'master' }

$Version = (python -c "from src.ai_write_x.version import get_version; print(get_version())").Trim()
$Tag = "v$Version"
$Setup = Join-Path $Root "dist\installer\AIWriteX-Setup.exe"
$DownloadUrl = "https://gitee.com/$Owner/$Repo/releases/download/$Tag/AIWriteX-Setup.exe"
$PolicyPath = Join-Path $Root 'version-policy.json'

if (-not (Test-Path $Setup)) {
    Write-Host "未找到安装包，请先运行 build_windows_installer.ps1" -ForegroundColor Red
    exit 1
}

$Policy = @{
    latest_version = $Version
    min_supported_version = '23.0.8'
    auto_update_on_startup = $true
    auto_update_silent = $true
    download_url = $DownloadUrl
    release_notes = "AIWriteX v$Version（Gitee 国内源）"
    published_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
}
$Policy | ConvertTo-Json -Depth 5 | Set-Content -Path $PolicyPath -Encoding UTF8

$Base = "https://gitee.com/api/v5/repos/$Owner/$Repo"
$Headers = @{ 'User-Agent' = 'AIWriteX-Publisher' }

Write-Host "Create Gitee Release $Tag ..."
$body = @{
    tag_name = $Tag
    name = "AIWriteX $Tag"
    body = $Policy.release_notes
    target_commitish = $Branch
    prerelease = $false
}

$existing = $null
try {
    $all = Invoke-RestMethod -Method Get -Uri "$Base/releases?access_token=$GITEE_TOKEN&per_page=20" -Headers $Headers
    foreach ($item in @($all)) {
        if ($item.tag_name -eq $Tag) {
            $existing = $item
            break
        }
    }
} catch {}

if ($existing -and $existing.id) {
    Write-Host "Release $Tag exists, delete and recreate..."
    Invoke-RestMethod -Method Delete -Uri "$Base/releases/$($existing.id)?access_token=$GITEE_TOKEN" -Headers $Headers | Out-Null
    Start-Sleep -Seconds 1
}

try {
    $release = Invoke-RestMethod -Method Post -Uri "$Base/releases?access_token=$GITEE_TOKEN" `
        -ContentType 'application/json; charset=utf-8' -Body ($body | ConvertTo-Json) -Headers $Headers
} catch {
    Write-Host "Create release failed:" -ForegroundColor Yellow
    Write-Host $_.Exception.Message
    exit 1
}

$ReleaseId = $release.id
if (-not $ReleaseId) {
    Write-Host "未获取到 Release ID" -ForegroundColor Red
    exit 1
}

function Upload-Attach($FilePath, $Label) {
    Write-Host "上传 $Label ..."
    $uri = "$Base/releases/$ReleaseId/attach_files?access_token=$GITEE_TOKEN"
    $form = @{ file = Get-Item -Path $FilePath }
    Invoke-RestMethod -Method Post -Uri $uri -Form $form -Headers $Headers | Out-Null
}

Upload-Attach $PolicyPath 'version-policy.json'
Upload-Attach $Setup 'AIWriteX-Setup.exe'

Write-Host ""
Write-Host "完成。Gitee Release:" -ForegroundColor Green
Write-Host "  https://gitee.com/$Owner/$Repo/releases/tag/$Tag"
Write-Host "  安装包: $DownloadUrl"
