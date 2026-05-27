# 发布到 Gitee / GitHub，并可选自动上传到宝塔服务器
# 用法:
#   1. 复制 gitee-release.env.example -> gitee-release.env，填写 GITEE_TOKEN
#   2. （推荐）复制 update-mirror.env.example -> update-mirror.env，填 IP/目录 → 发版自动 scp
#   3. 先 build: .\build_windows_installer.ps1
#   4. powershell -ExecutionPolicy Bypass -File .\scripts\publish-gitee-release.ps1
#   或一键: .\scripts\publish-all.ps1

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

$MirrorEnvFile = Join-Path $Root 'scripts\update-mirror.env'
if (Test-Path $MirrorEnvFile) {
    Get-Content $MirrorEnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            if (-not (Get-Variable -Name $name -Scope Script -ErrorAction SilentlyContinue)) {
                Set-Variable -Name $name -Value $matches[2].Trim() -Scope Script
            }
        }
    }
}

$Owner = if ($GITEE_OWNER) { $GITEE_OWNER } else { 'lqyha520' }
$Repo = if ($GITEE_REPO) { $GITEE_REPO } else { 'AIWriteX-main' }
$Branch = if ($GITEE_BRANCH) { $GITEE_BRANCH } else { 'master' }

$Version = (python -c "from src.ai_write_x.version import get_version; print(get_version())").Trim()
$Tag = "v$Version"
$SetupDir = Join-Path $Root 'dist\installer'
$SetupItem = Get-ChildItem -Path $SetupDir -Filter '*-Setup.exe' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $SetupItem) {
    Write-Host "未找到安装包，请先运行 build_windows_installer.ps1" -ForegroundColor Red
    exit 1
}
$Setup = $SetupItem.FullName
$InstallerName = $SetupItem.Name
$PolicyPath = Join-Path $Root 'version-policy.json'
$SkipExeUpload = $false

$EncodedInstaller = [uri]::EscapeDataString($InstallerName)
$DownloadUrl = "https://gitee.com/$Owner/$Repo/releases/download/$Tag/$EncodedInstaller"
if ($MIRROR_BASE_URL) {
    $DownloadUrl = "$($MIRROR_BASE_URL.TrimEnd('/'))/$InstallerName"
    Write-Host "使用腾讯云镜像下载地址 (update-mirror.env):" -ForegroundColor Cyan
    Write-Host "  $DownloadUrl"
    if ($SetupItem.Length -gt 100MB) {
        $SkipExeUpload = $true
    }
} elseif ($SetupItem.Length -gt 100MB) {
    Write-Host "安装包超过 100MB，请在 scripts\update-mirror.env 配置 MIRROR_BASE_URL 与 SSH 后重试。" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $Setup)) {
    Write-Host "未找到安装包，请先运行 build_windows_installer.ps1" -ForegroundColor Red
    exit 1
}

$Policy = @{
    latest_version = $Version
    min_supported_version = $Version
    auto_update_on_startup = $true
    auto_update_silent = $true
    download_url = $DownloadUrl
    release_notes = "小爆来咯 v${Version} 正式版"
    published_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
}
$json = $Policy | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($PolicyPath, $json + "`n", [System.Text.UTF8Encoding]::new($false))

$Base = "https://gitee.com/api/v5/repos/$Owner/$Repo"
$Headers = @{ 'User-Agent' = 'AIWriteX-Publisher' }

Write-Host "Create Gitee Release $Tag ..."
$body = @{
    tag_name = $Tag
    name = "小爆来咯 $Tag"
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
} catch {
    # ignore list failures
}

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
    Write-Host "Upload $Label ..."
    $uri = "$Base/releases/$ReleaseId/attach_files?access_token=$GITEE_TOKEN"
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        & curl.exe -sS -X POST $uri -F "file=@$FilePath"
        if ($LASTEXITCODE -ne 0) {
            throw "curl upload failed for $Label (exit $LASTEXITCODE)"
        }
        return
    }

    Add-Type -AssemblyName System.Net.Http
    $client = New-Object System.Net.Http.HttpClient
    $content = New-Object System.Net.Http.MultipartFormDataContent
    $stream = [System.IO.File]::OpenRead($FilePath)
    $fileContent = New-Object System.Net.Http.StreamContent($stream)
    $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse('application/octet-stream')
    $content.Add($fileContent, 'file', [System.IO.Path]::GetFileName($FilePath))
    $response = $client.PostAsync($uri, $content).GetAwaiter().GetResult()
    $stream.Close()
    if (-not $response.IsSuccessStatusCode) {
        $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        throw "Upload failed for ${Label}: $($response.StatusCode) $body"
    }
}

Upload-Attach $PolicyPath 'version-policy.json'
if (-not $SkipExeUpload) {
    Upload-Attach $Setup $InstallerName
} else {
    Write-Host "Skip exe upload (Gitee 100MB limit). Users download via download_url in version-policy.json"
}

# 只保留最新 Release，避免旧 tag 排在 API 前列导致客户端误判版本
try {
    $all = Invoke-RestMethod -Method Get -Uri "$Base/releases?access_token=$GITEE_TOKEN&per_page=50" -Headers $Headers
    foreach ($item in @($all)) {
        if ($item.tag_name -and $item.tag_name -ne $Tag -and $item.id) {
            Write-Host "Delete old release $($item.tag_name) ..."
            Invoke-RestMethod -Method Delete -Uri "$Base/releases/$($item.id)?access_token=$GITEE_TOKEN" -Headers $Headers | Out-Null
        }
    }
} catch {
    Write-Host "Cleanup old releases skipped: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "完成。Gitee Release:" -ForegroundColor Green
Write-Host "  https://gitee.com/$Owner/$Repo/releases/tag/$Tag"
Write-Host "  安装包: $DownloadUrl"

if ($MIRROR_BASE_URL -and $SSH_HOST) {
    Write-Host ""
    Write-Host "Upload to mirror server..." -ForegroundColor Cyan
    $deployScript = Join-Path $Root 'scripts\deploy-update-mirror.ps1'
    & powershell.exe -ExecutionPolicy Bypass -File $deployScript -PolicyFile $PolicyPath -SetupFile $Setup
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Mirror upload failed. Check update-mirror.env and SSH." -ForegroundColor Yellow
        exit $LASTEXITCODE
    }
} elseif ($MIRROR_BASE_URL -and -not $SSH_HOST) {
    Write-Host ""
    Write-Host "Mirror URL set but SSH_HOST missing. Upload manually:" -ForegroundColor Yellow
    Write-Host "  $Setup  ->  $InstallerName"
    Write-Host "  $PolicyPath  ->  version-policy.json"
    Write-Host "  Target: $MIRROR_BASE_URL"
}

try {
    $gh = Get-Command gh.exe -ErrorAction SilentlyContinue
    if ($gh -and (Test-Path $Setup) -and (Test-Path $PolicyPath)) {
        Write-Host ""
        Write-Host "同步 GitHub Release $Tag ..." -ForegroundColor Cyan
        gh release view $Tag --repo "$Owner/$Repo" 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            gh release create $Tag $Setup $PolicyPath --repo "$Owner/$Repo" `
                --title "小爆来咯 $Tag" --notes $Policy.release_notes --latest
        } else {
            gh release upload $Tag $Setup $PolicyPath --repo "$Owner/$Repo" --clobber
        }
        $listed = gh release list --repo "$Owner/$Repo" --limit 20 2>$null
        if ($listed) {
            foreach ($line in ($listed -split "`n")) {
                if ($line -match '\tv([0-9.]+)\t') {
                    $oldTag = 'v' + $Matches[1]
                    if ($oldTag -ne $Tag) {
                        Write-Host "Delete old GitHub release $oldTag ..."
                        gh release delete $oldTag --repo "$Owner/$Repo" --yes 2>$null
                    }
                }
            }
        }
        Write-Host "GitHub: https://github.com/$Owner/$Repo/releases/tag/$Tag" -ForegroundColor Green
    }
} catch {
    Write-Host "GitHub publish skipped: $($_.Exception.Message)" -ForegroundColor Yellow
}
