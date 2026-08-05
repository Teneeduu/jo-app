<#
.SYNOPSIS
    给 jo-app 建桌面 / 开始菜单快捷方式。

.DESCRIPTION
    jo-app 没有独立的 exe —— 它跑在 pythonw.exe 上（用 pythonw 而不是 python，
    双击时才不会弹一个黑框）。这个脚本建的快捷方式指向虚拟环境里的 pythonw，
    参数是 -m joapp，图标用 joapp/resources/jo-app.ico。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\create_shortcut.ps1
    powershell -ExecutionPolicy Bypass -File .\scripts\create_shortcut.ps1 -StartMenu
    powershell -ExecutionPolicy Bypass -File .\scripts\create_shortcut.ps1 -Remove
#>
param(
    [switch]$StartMenu,      # 同时在开始菜单放一个
    [switch]$Remove,         # 删掉而不是创建
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$linkName    = "jo-app.lnk"

$targets = @([Environment]::GetFolderPath("Desktop"))
if ($StartMenu) {
    $targets += Join-Path ([Environment]::GetFolderPath("ApplicationData")) "Microsoft\Windows\Start Menu\Programs"
}

if ($Remove) {
    foreach ($dir in $targets) {
        $path = Join-Path $dir $linkName
        if (Test-Path $path) { Remove-Item $path -Force; Write-Host "已删除 $path" -ForegroundColor Green }
        else { Write-Host "没找到 $path" -ForegroundColor Yellow }
    }
    return
}

# 找 pythonw.exe：优先参数，其次项目里的 venv，最后 PATH
if (-not $Python) {
    $venvPythonw = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
    if (Test-Path $venvPythonw) {
        $Python = $venvPythonw
    } else {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if (-not $cmd) { throw "找不到 python。先建虚拟环境，或者用 -Python 指定 pythonw.exe。" }
        $candidate = Join-Path (Split-Path -Parent $cmd.Source) "pythonw.exe"
        $Python = if (Test-Path $candidate) { $candidate } else { $cmd.Source }
    }
}
if (-not (Test-Path $Python)) { throw "找不到解释器: $Python" }

# 图标是画出来的，缺了就现生成一个
$icon = Join-Path $projectRoot "joapp\resources\jo-app.ico"
if (-not (Test-Path $icon)) {
    $gen = Join-Path $projectRoot "scripts\make_icon.py"
    $pythonExe = $Python -replace "pythonw\.exe$", "python.exe"
    if ((Test-Path $gen) -and (Test-Path $pythonExe)) {
        Write-Host "图标不存在，正在生成……"
        & $pythonExe $gen | Out-Null
    }
}

$shell = New-Object -ComObject WScript.Shell
foreach ($dir in $targets) {
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $path = Join-Path $dir $linkName
    $link = $shell.CreateShortcut($path)
    $link.TargetPath       = $Python
    $link.Arguments        = "-m joapp"
    $link.WorkingDirectory = $projectRoot
    $link.Description      = "jo-app - 每天开机问你一句"
    if (Test-Path $icon) { $link.IconLocation = "$icon,0" }
    $link.Save()
    Write-Host "已创建 $path" -ForegroundColor Green
}

Write-Host ""
Write-Host "  解释器 : $Python"
Write-Host "  参数   : -m joapp"
Write-Host "  图标   : $(if (Test-Path $icon) { $icon } else { '（没有 .ico，用解释器默认图标）' })"
Write-Host ""
Write-Host "提示：jo-app 是托盘应用，双击后不会有窗口 —— 看右下角托盘区。"
