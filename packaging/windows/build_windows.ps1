# Build GitDesk for Windows 11 / 10 (x64) and create the installer.
# Requirements: Python 3.10+ (python.org), Inno Setup 6 (https://jrsoftware.org/isdl.php)
# Usage (PowerShell, from the project root):   .\packaging\windows\build_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")

python -m venv .venv-build
.\.venv-build\Scripts\python -m pip install --upgrade pip
.\.venv-build\Scripts\python -m pip install -r requirements.txt pyinstaller

.\.venv-build\Scripts\python packaging\make_icons.py
.\.venv-build\Scripts\pyinstaller packaging\gitdesk.spec --noconfirm --distpath dist --workpath build

$version = (Select-String -Path gitdesk\__init__.py -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 (ISCC.exe) not found. Install it from https://jrsoftware.org/isdl.php" }
& $iscc "/DAppVersion=$version" packaging\windows\GitDesk.iss

Compress-Archive -Force -Path dist\GitDesk\* -DestinationPath "dist\GitDesk-$version-windows-x64-portable.zip"
Write-Host "Done: dist\GitDesk-Setup-$version.exe and the portable zip"
