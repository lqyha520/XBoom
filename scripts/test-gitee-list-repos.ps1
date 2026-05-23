$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Get-Content (Join-Path $Root 'scripts\gitee-release.env') | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
        Set-Variable -Name $matches[1].Trim() -Value $matches[2].Trim() -Scope Script
    }
}
$list = Invoke-RestMethod -Uri "https://gitee.com/api/v5/user/repos?access_token=$GITEE_TOKEN&per_page=20" -Headers @{ 'User-Agent' = 'AIWriteX' }
foreach ($item in @($list)) {
    if ($item.name -like '*AIWrite*') {
        Write-Host "$($item.full_name) public=$($item.public) private=$($item.private)"
    }
}
