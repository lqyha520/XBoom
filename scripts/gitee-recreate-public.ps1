# Recreate Gitee repo as PUBLIC and republish release
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Get-Content (Join-Path $Root 'scripts\gitee-release.env') | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
        Set-Variable -Name $matches[1].Trim() -Value $matches[2].Trim() -Scope Script
    }
}

$Owner = if ($GITEE_OWNER) { $GITEE_OWNER } else { 'lqyha520' }
$Repo = if ($GITEE_REPO) { $GITEE_REPO } else { 'XBoom' }
$Branch = if ($GITEE_BRANCH) { $GITEE_BRANCH } else { 'master' }
$Base = "https://gitee.com/api/v5"
$H = @{ 'User-Agent' = 'AIWriteX' }

Write-Host "Delete old repo (if any)..."
try {
    Invoke-RestMethod -Method Delete -Uri "$Base/repos/$Owner/$Repo?access_token=$GITEE_TOKEN" -Headers $H | Out-Null
    Start-Sleep -Seconds 2
} catch {}

Write-Host "Create PUBLIC repo..."
$createBody = @{
    access_token = $GITEE_TOKEN
    name = $Repo
    description = 'AIWriteX CN update mirror'
    private = 'false'
    has_issues = 'false'
    has_wiki = 'false'
    auto_init = 'true'
}
Invoke-RestMethod -Method Post -Uri "$Base/user/repos" -Body $createBody -Headers $H | Out-Null
Start-Sleep -Seconds 2

$list = Invoke-RestMethod -Uri "$Base/user/repos?access_token=$GITEE_TOKEN&per_page=50" -Headers $H
$item = @($list) | Where-Object { $_.name -eq $Repo } | Select-Object -First 1
Write-Host "public=$($item.public) private=$($item.private)"

& (Join-Path $Root 'scripts\publish-gitee-release.ps1')

