$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

python -m pip install -r requirements.txt
python -m pip install pyinstaller

pyinstaller `
  --noconfirm `
  --onefile `
  --windowed `
  --name BoxLinkOpener `
  box_link_opener.py

Write-Host ""
Write-Host "Build complete:"
Write-Host "$ScriptDir\dist\BoxLinkOpener.exe"
