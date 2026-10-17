# 一键构建三个 exe：主程序、卸载器、安装器
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$PY = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$PYI = Join-Path $PSScriptRoot '.venv\Scripts\pyinstaller.exe'

Write-Host '[1/3] 构建主程序 DualSenseBatteryHotkey.exe' -ForegroundColor Cyan
& $PYI --onefile --windowed --name DualSenseBatteryHotkey --icon icon.ico main.py
if ($LASTEXITCODE -ne 0) { throw '主程序构建失败' }

Write-Host '[2/3] 构建卸载器 Uninstall.exe' -ForegroundColor Cyan
& $PYI --onefile --windowed --name Uninstall --icon icon.ico uninstaller.py
if ($LASTEXITCODE -ne 0) { throw '卸载器构建失败' }

Write-Host '[3/3] 构建安装器 Setup.exe' -ForegroundColor Cyan
& $PYI --onefile --windowed --name Setup --icon icon.ico `
  --add-data 'dist/DualSenseBatteryHotkey.exe;.' `
  --add-data 'dist/Uninstall.exe;.' installer.py
if ($LASTEXITCODE -ne 0) { throw '安装器构建失败' }

Write-Host ''
Write-Host '构建完成，产物在 dist/ 目录：' -ForegroundColor Green
Get-ChildItem (Join-Path $PSScriptRoot 'dist') -Filter '*.exe' | ForEach-Object {
    Write-Host ('  {0}  ({1:N1} MB)' -f $_.Name, ($_.Length / 1MB))
}
