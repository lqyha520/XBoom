$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Get-Content (Join-Path $Root 'scripts\gitee-release.env') | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
        Set-Variable -Name $matches[1].Trim() -Value $matches[2].Trim() -Scope Script
    }
}
$Owner = if ($GITEE_OWNER) { $GITEE_OWNER } else { 'lqyha520' }
$Repo = if ($GITEE_REPO) { $GITEE_REPO } else { 'AIWriteX-main' }
$body = '{"private":false}'
Invoke-RestMethod -Method Patch -Uri "https://gitee.com/api/v5/repos/$Owner/$Repo?access_token=$GITEE_TOKEN" `
    -ContentType 'application/json; charset=utf-8' -Body $body -Headers @{ 'User-Agent' = 'AIWriteX' } | Out-Null
Write-Host "Repo is now public: https://gitee.com/$Owner/$Repo" -ForegroundColor Green
