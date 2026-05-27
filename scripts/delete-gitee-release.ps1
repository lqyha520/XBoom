param(
    [Parameter(Mandatory = $true)]
    [string]$Tag
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
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
$Base = "https://gitee.com/api/v5/repos/$Owner/$Repo"
$Headers = @{ 'User-Agent' = 'AIWriteX-Publisher' }

$uri = "$Base/releases?access_token=$GITEE_TOKEN" + '&per_page=50'
$all = Invoke-RestMethod -Method Get -Uri $uri -Headers $Headers
$target = $null
foreach ($item in @($all)) {
    if ($item.tag_name -eq $Tag) {
        $target = $item
        break
    }
}
if (-not $target) {
    Write-Host "未找到 Release $Tag"
    exit 0
}

Write-Host "Deleting $Tag (id=$($target.id)) ..."
$delUri = "$Base/releases/$($target.id)?access_token=$GITEE_TOKEN"
Invoke-RestMethod -Method Delete -Uri $delUri -Headers $Headers | Out-Null
Write-Host "Done."
