# Setup Gitee repo + Release for CN auto-update
# Requires GITEE_TOKEN in scripts\gitee-release.env

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$EnvFile = Join-Path $Root 'scripts\gitee-release.env'
if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $Root 'scripts\gitee-release.env.example') $EnvFile
    Write-Host "Created $EnvFile - add GITEE_TOKEN and rerun." -ForegroundColor Yellow
    Write-Host "https://gitee.com/profile/personal_access_tokens"
    exit 1
}

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
        Set-Variable -Name $matches[1].Trim() -Value $matches[2].Trim() -Scope Script
    }
}

if (-not $GITEE_TOKEN) {
    Write-Host "Set GITEE_TOKEN in $EnvFile" -ForegroundColor Red
    exit 1
}

$Owner = if ($GITEE_OWNER) { $GITEE_OWNER } else { 'lqyha520' }
$Repo = if ($GITEE_REPO) { $GITEE_REPO } else { 'XBoom' }
$ApiBase = "https://gitee.com/api/v5"
$Headers = @{ 'User-Agent' = 'AIWriteX-Setup' }

function Invoke-GiteeApi {
    param([string]$Method, [string]$Path, [object]$Body = $null)
    $uri = "$ApiBase$Path" + "?access_token=$GITEE_TOKEN"
    $params = @{ Method = $Method; Uri = $uri; Headers = $Headers }
    if ($null -ne $Body) {
        $params.ContentType = 'application/json; charset=utf-8'
        $params.Body = ($Body | ConvertTo-Json -Depth 6 -Compress)
    }
    return Invoke-RestMethod @params
}

Write-Host "Check repo $Owner/$Repo ..."
$repoExists = $false
$checkUri = "$ApiBase/repos/$Owner/$Repo" + "?access_token=$GITEE_TOKEN"
try {
    Invoke-RestMethod -Method Get -Uri $checkUri -Headers $Headers | Out-Null
    $repoExists = $true
    Write-Host "Repo exists." -ForegroundColor Green
} catch {
    $repoExists = $false
}

if (-not $repoExists) {
    Write-Host "Creating public repo $Repo ..."
    Invoke-GiteeApi -Method Post -Path '/user/repos' -Body @{
        name = $Repo
        description = 'AIWriteX CN update mirror'
        private = $false
        has_issues = $false
        has_wiki = $false
        auto_init = $true
    } | Out-Null
    Write-Host "Repo created." -ForegroundColor Green
    Start-Sleep -Seconds 2
}

$SetupItem = Get-ChildItem -Path (Join-Path $Root 'dist\installer') -Filter '*-Setup.exe' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$Setup = if ($SetupItem) { $SetupItem.FullName } else { $null }
if (-not (Test-Path $Setup)) {
    Write-Host "Building installer..."
    & (Join-Path $Root 'build_windows_installer.ps1')
}

Write-Host "Publishing release..."
& (Join-Path $Root 'scripts\publish-gitee-release.ps1')
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Verify releases..."
$releases = Invoke-GiteeApi -Method Get -Path "/repos/$Owner/$Repo/releases"
if (-not $releases -or @($releases).Count -lt 1) {
    Write-Host "No releases found." -ForegroundColor Yellow
    exit 1
}

$latest = @($releases)[0]
Write-Host "Latest: $($latest.tag_name)" -ForegroundColor Green
Write-Host "https://gitee.com/$Owner/$Repo/releases"

