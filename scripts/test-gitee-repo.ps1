$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Get-Content (Join-Path $Root 'scripts\gitee-release.env') | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
        Set-Variable -Name $matches[1].Trim() -Value $matches[2].Trim() -Scope Script
    }
}
$r = Invoke-RestMethod -Uri "https://gitee.com/api/v5/repos/$GITEE_OWNER/$GITEE_REPO?access_token=$GITEE_TOKEN" -Headers @{ 'User-Agent' = 'AIWriteX' }
Write-Host "name=$($r.name) public=$($r.public) path=$($r.path)"
Write-Host $r.html_url
