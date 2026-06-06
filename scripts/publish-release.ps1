# 鍙戝竷褰撳墠鐗堟湰鍒?GitHub Release锛堜緵鑷姩鏇存柊鎷夊彇锛?
# 鐢ㄦ硶锛氬厛 gh auth login锛屽啀鍦ㄦ湰鐩綍鎵ц锛?
#   powershell -ExecutionPolicy Bypass -File .\scripts\publish-release.ps1

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Version = (python -c "from src.ai_write_x.version import get_version; print(get_version())").Trim()
$Tag = "v$Version"
$SetupItem = Get-ChildItem -Path (Join-Path $Root 'dist\installer') -Filter '*-Setup.exe' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$Setup = if ($SetupItem) { $SetupItem.FullName } else { $null }
$Policy = Join-Path $Root "version-policy.json"

if (-not (Test-Path $Setup)) {
    Write-Host "鏈壘鍒板畨瑁呭寘锛岃鍏堣繍琛? .\build_windows_installer.ps1" -ForegroundColor Red
    exit 1
}

gh auth status | Out-Null

Write-Host "鎺ㄩ€佷唬鐮佸埌 origin/main ..."
git push origin main

Write-Host "鍒涘缓 Release $Tag ..."
$uploadOk = $false
try {
    gh release upload $Tag $Setup $Policy --clobber 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $uploadOk = $true }
} catch {}

if (-not $uploadOk) {
    gh release create $Tag $Setup $Policy `
        --title "灏忕垎鏉ュ挴 $Tag" `
        --notes-file $Policy `
        --latest
}

Write-Host "瀹屾垚銆俁elease: https://github.com/lqyha520/XBoom/releases/tag/$Tag" -ForegroundColor Green

