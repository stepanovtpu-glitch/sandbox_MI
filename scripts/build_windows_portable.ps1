param(
  [string]$AppName = "GasMeterPro",
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$BuildTools = Join-Path $Root "build\package-tools"
$ToolsDir = Join-Path $BuildTools "tools"
$ReleaseRoot = Join-Path $Root "release"
$ReleaseDir = Join-Path $ReleaseRoot $AppName
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$Npm = "C:\Program Files\nodejs\npm.cmd"

function Require-File($Path, $Message) {
  if (!(Test-Path $Path)) {
    throw "$Message`nMissing: $Path"
  }
}

function Copy-Directory($Source, $Target) {
  if (Test-Path $Target) {
    Remove-Item -Recurse -Force $Target
  }
  New-Item -ItemType Directory -Force -Path (Split-Path $Target -Parent) | Out-Null
  Copy-Item -Recurse -Force $Source $Target
}

function Run-Checked($FilePath, $Arguments, $WorkingDirectory = $null) {
  if ($WorkingDirectory) {
    Push-Location $WorkingDirectory
  }
  try {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
      throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
  } finally {
    if ($WorkingDirectory) {
      Pop-Location
    }
  }
}

Require-File $Python "Backend virtual environment is required. Create it before packaging."
Require-File $Npm "Node.js/npm is required on the build machine."

Write-Host "==> Installing backend build dependencies"
Run-Checked $Python @("-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", (Join-Path $Backend "requirements.txt"))
Run-Checked $Python @("-m", "pip", "install", "--disable-pip-version-check", "-q", "pyinstaller")

Write-Host "==> Building frontend"
Run-Checked $Npm @("run", "build") $Frontend

Write-Host "==> Preparing bundled OCR/PDF tools"
New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null

$TesseractDir = "C:\Program Files\Tesseract-OCR"
if (!(Test-Path (Join-Path $TesseractDir "tesseract.exe"))) {
  $TesseractDir = "C:\Program Files (x86)\Tesseract-OCR"
}
Require-File (Join-Path $TesseractDir "tesseract.exe") "Tesseract must be installed on the build machine."
Copy-Directory $TesseractDir (Join-Path $ToolsDir "tesseract")
Copy-Item -Force (Join-Path $Backend "app\ocr_tessdata\*.traineddata") (Join-Path $ToolsDir "tesseract\tessdata")

$PopplerBin = $env:POPPLER_BIN
if (!$PopplerBin) {
  $PopplerBin = Join-Path $HOME ".cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin"
}
Require-File (Join-Path $PopplerBin "pdftoppm.exe") "Poppler pdftoppm.exe must be available on the build machine. Set POPPLER_BIN if needed."
New-Item -ItemType Directory -Force -Path (Join-Path $ToolsDir "poppler") | Out-Null
Copy-Directory $PopplerBin (Join-Path $ToolsDir "poppler\bin")

Write-Host "==> Creating PyInstaller executable"
Get-Process $AppName -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item -Recurse -Force (Join-Path $Root "build\$AppName") -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force (Join-Path $Root "dist\$AppName") -ErrorAction SilentlyContinue
Run-Checked $Python @(
  "-m", "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onedir",
  "--name", $AppName,
  "--paths", $Backend,
  "--add-data", "$Frontend\dist;frontend",
  "--add-data", "$ToolsDir;tools",
  "$Backend\desktop_server.py"
) $Root

Write-Host "==> Preparing release folder"
if (Test-Path $ReleaseDir) {
  Remove-Item -Recurse -Force $ReleaseDir
}
New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null
Copy-Directory (Join-Path $Root "dist\$AppName") $ReleaseDir
New-Item -ItemType Directory -Force -Path (Join-Path $ReleaseDir "data") | Out-Null

$StartBat = @"
@echo off
setlocal
cd /d "%~dp0"
set GASMETER_DB_DIR=%~dp0data
start "" "http://127.0.0.1:$Port/"
"%~dp0$AppName.exe" --host 127.0.0.1 --port $Port
endlocal
"@
$StartBat | Set-Content -Path (Join-Path $ReleaseDir "start-gasmeter.bat") -Encoding ASCII

$Readme = @"
GasMeter Pro portable alpha

How to run:
1. Open start-gasmeter.bat
2. Browser will open http://127.0.0.1:$Port/
3. All user data is stored in the local data folder.

Do not delete the data folder if you need to keep methods, PDFs, reports, and calculation history.
"@
$Readme | Set-Content -Path (Join-Path $ReleaseDir "README_RUN.txt") -Encoding UTF8

Write-Host "==> Done: $ReleaseDir"
