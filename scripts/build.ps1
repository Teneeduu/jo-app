<#
.SYNOPSIS
  打包 jo-app：PyInstaller 出 exe，Inno Setup 出安装程序。
  本机和 GitHub Actions（.github/workflows/release.yml）跑的是同一个脚本。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1               # exe + 安装程序
  powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1 -NoInstaller  # 只出 exe（没装 Inno Setup 时）

  产物：build\dist\jo-app\jo-app.exe（免安装，整个文件夹拷走就能用）
        dist\jo-app-setup.exe（安装程序）
#>
param(
    [switch]$NoInstaller,
    [string]$Python,  # 默认用 .venv 里的，没有就用 PATH 上的 python
    [string]$Iscc     # Inno Setup 的 ISCC.exe，默认在常见位置找
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $Python) {
    $venv = Join-Path $root '.venv\Scripts\python.exe'
    $Python = if (Test-Path $venv) { $venv } else { 'python' }
}
$version = (& $Python -c "import joapp; print(joapp.__version__)").Trim()
Write-Host "== jo-app $version =="

Write-Host "== PyInstaller =="
& $Python -m pip install --quiet --disable-pip-version-check "pyinstaller>=6.10"
if ($LASTEXITCODE) { throw "装 PyInstaller 失败" }

& $Python -m PyInstaller --noconfirm --clean --windowed `
    --name jo-app `
    --icon (Join-Path $root 'joapp\resources\jo-app.ico') `
    --paths $root `
    --distpath (Join-Path $root 'build\dist') `
    --workpath (Join-Path $root 'build\work') `
    --specpath (Join-Path $root 'build') `
    --exclude-module tkinter `
    (Join-Path $root 'packaging\launcher.py')
if ($LASTEXITCODE) { throw "PyInstaller 失败" }
$exe = Join-Path $root 'build\dist\jo-app\jo-app.exe'
if (-not (Test-Path $exe)) { throw "没找到 $exe" }

# PyInstaller 按「可能用到」收 Qt 文件，纯 Widgets 应用用不上的删掉（120 MB → 一半左右）：
# 软件渲染的 OpenGL、QML/Quick、PDF、虚拟键盘，以及 QLocalSocket 用不到的 TLS 后端。
# 删了对应插件，Qt 启动时就不会去加载它们。
$qt = Join-Path $root 'build\dist\jo-app\_internal\PySide6'
$prune = @(
    'opengl32sw.dll', 'Qt6Pdf.dll', 'Qt6Qml*.dll', 'Qt6Quick*.dll', 'Qt6VirtualKeyboard*.dll',
    'plugins\imageformats\qpdf.dll', 'plugins\platforminputcontexts', 'plugins\tls'
)
foreach ($p in $prune) { Remove-Item (Join-Path $qt $p) -Recurse -Force -ErrorAction SilentlyContinue }
# 翻译只留简体中文（确认框的「是 / 否」按钮用得到）
Get-ChildItem (Join-Path $qt 'translations') -File |
    Where-Object { $_.Name -notlike '*zh_CN.qm' } | Remove-Item -Force
$mb = (Get-ChildItem (Split-Path $exe) -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("exe: {0}（整个目录 {1:N0} MB）" -f $exe, $mb)

if ($NoInstaller) { return }

Write-Host "== Inno Setup =="
if (-not $Iscc) {
    $found = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($found) { $Iscc = $found.Source }
}
if (-not $Iscc) {
    $candidates = foreach ($v in '7', '6') {
        "${env:ProgramFiles}\Inno Setup $v\ISCC.exe"
        "${env:ProgramFiles(x86)}\Inno Setup $v\ISCC.exe"
        "${env:LOCALAPPDATA}\Programs\Inno Setup $v\ISCC.exe"
    }
    $Iscc = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}
if (-not $Iscc) {
    throw "没找到 Inno Setup 的 ISCC.exe。装一个 Inno Setup 7（https://jrsoftware.org/isdl.php），或者加 -NoInstaller 只打 exe。"
}

& $Iscc "/DAppVersion=$version" (Join-Path $root 'packaging\installer.iss')
if ($LASTEXITCODE) { throw "Inno Setup 编译失败" }
Write-Host "安装程序: $(Join-Path $root 'dist\jo-app-setup.exe')"
