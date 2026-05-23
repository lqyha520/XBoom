$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Get-Content (Join-Path $Root 'scripts\gitee-release.env') | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
        Set-Variable -Name $matches[1].Trim() -Value $matches[2].Trim() -Scope Script
    }
}
$uri = "https://gitee.com/api/v5/repos/$GITEE_OWNER/$GITEE_REPO/releases/tags/v23.0.9?access_token=$GITEE_TOKEN"
$r = Invoke-RestMethod -Uri $uri -Headers @{ 'User-Agent' = 'AIWriteX' }
Write-Host "tag=$($r.tag_name) assets=$(@($r.assets).Count)"
foreach ($a in @($r.assets)) { Write-Host " - $($a.name)" }
