<#
.SYNOPSIS
    取消 jo-app 的开机自启。
#>
$ErrorActionPreference = "Stop"

$linkPath = Join-Path ([Environment]::GetFolderPath("Startup")) "jo-app.lnk"

if (Test-Path $linkPath) {
    Remove-Item $linkPath -Force
    Write-Host "已移除开机自启: $linkPath" -ForegroundColor Green
} else {
    Write-Host "本来就没注册过，无事发生。" -ForegroundColor Yellow
}
