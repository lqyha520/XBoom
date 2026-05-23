# Push version-policy.json to Gitee repo (public raw URL for all clients)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$EnvFile = Join-Path $Root 'scripts\gitee-release.env'
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
        Set-Variable -Name $matches[1].Trim() -Value $matches[2].Trim() -Scope Script
    }
}

$Owner = if ($GITEE_OWNER) { $GITEE_OWNER } else { 'lqyha520' }
$Repo = if ($GITEE_REPO) { $GITEE_REPO } else { 'AIWriteX-main' }
$Branch = if ($GITEE_BRANCH) { $GITEE_BRANCH } else { 'master' }
$Path = 'releases/version-policy.json'
$File = Join-Path $Root 'version-policy.json'
$uri = "https://gitee.com/api/v5/repos/$Owner/$Repo/contents/$Path"
$Headers = @{ 'User-Agent' = 'AIWriteX' }

$content = [Convert]::ToBase64String([IO.File]::ReadAllBytes($File))
$body = @{
    access_token = $GITEE_TOKEN
    content = $content
    message = 'update version-policy.json'
    branch = $Branch
}

$existing = $null
try {
    $existing = Invoke-RestMethod -Uri "$uri`?access_token=$GITEE_TOKEN&ref=$Branch" -Headers $Headers
} catch {}

if ($existing -and $existing.sha) {
    $body.sha = $existing.sha
}

Invoke-RestMethod -Method Put -Uri $uri -ContentType 'application/json; charset=utf-8' `
    -Body ($body | ConvertTo-Json) -Headers $Headers | Out-Null

Write-Host "https://gitee.com/$Owner/$Repo/raw/$Branch/$Path" -ForegroundColor Green
