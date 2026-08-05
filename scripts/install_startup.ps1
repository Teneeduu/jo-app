<#
.SYNOPSIS
    把 jo-app 注册成开机自启（当前用户）。

.DESCRIPTION
    在「启动」文件夹里放一个快捷方式，指向 pythonw.exe -m joapp。
    用 pythonw 而不是 python，开机时才不会闪出一个黑框。
    卸载跑 uninstall_startup.ps1。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\install_startup.ps1
    powershell -ExecutionPolicy Bypass -File .\scripts\install_startup.ps1 -Python "D:\venv\Scripts\pythonw.exe"
#>
param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot

# 找 pythonw.exe：优先参数，其次同目录 venv，最后 PATH 上的 python
if (-not $Python) {
    $venvPythonw = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
    if (Test-Path $venvPythonw) {
        $Python = $venvPythonw
    } else {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if (-not $cmd) { throw "PATH 上找不到 python，用 -Python 指定 pythonw.exe 的路径。" }
        $candidate = Join-Path (Split-Path -Parent $cmd.Source) "pythonw.exe"
        $Python = if (Test-Path $candidate) { $candidate } else { $cmd.Source }
    }
}

if (-not (Test-Path $Python)) { throw "找不到解释器: $Python" }

$startup  = [Environment]::GetFolderPath("Startup")
$linkPath = Join-Path $startup "jo-app.lnk"

$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($linkPath)
$link.TargetPath       = $Python
$link.Arguments        = "-m joapp"
$link.WorkingDirectory = $projectRoot
$link.Description      = "jo-app - 每天开机问你一句"
$link.WindowStyle      = 7    # 最小化启动
$link.Save()

Write-Host "已注册开机自启" -ForegroundColor Green
Write-Host "  快捷方式 : $linkPath"
Write-Host "  解释器   : $Python"
Write-Host "  工作目录 : $projectRoot"
Write-Host ""
Write-Host "现在试跑一次: `"$Python`" -m joapp"
