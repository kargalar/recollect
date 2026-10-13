$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$dist = Join-Path $root 'dist'
$staging = Join-Path $dist 'Recollect-Windows-x64'
$pyInstaller = Join-Path $root '.venv/Scripts/pyinstaller.exe'

if (-not (Test-Path -LiteralPath $pyInstaller)) {
    throw 'Create .venv, install requirements.txt, then install PyInstaller in that environment.'
}

New-Item -ItemType Directory -Path $staging -Force | Out-Null

& $pyInstaller --noconfirm --clean --onefile --windowed --name Recollect (Join-Path $root 'app/tray.py')
if ($LASTEXITCODE -ne 0) { throw 'Could not build Recollect.exe.' }

& $pyInstaller --noconfirm --clean --onefile --windowed --name RecollectApi --add-data "$(Join-Path $root 'app/static');static" (Join-Path $root 'app/api_entry.py')
if ($LASTEXITCODE -ne 0) { throw 'Could not build RecollectApi.exe.' }

& $pyInstaller --noconfirm --clean --onefile --windowed --name RecollectRecorder (Join-Path $root 'app/recorder.py')
if ($LASTEXITCODE -ne 0) { throw 'Could not build RecollectRecorder.exe.' }

Copy-Item -LiteralPath (Join-Path $dist 'Recollect.exe') -Destination $staging
Copy-Item -LiteralPath (Join-Path $dist 'RecollectApi.exe') -Destination $staging
Copy-Item -LiteralPath (Join-Path $dist 'RecollectRecorder.exe') -Destination $staging
Copy-Item -LiteralPath (Join-Path $root 'app/static') -Destination $staging -Recurse
Copy-Item -LiteralPath (Join-Path $root 'README.md') -Destination $staging
Copy-Item -LiteralPath (Join-Path $root 'LICENSE') -Destination $staging

$archive = Join-Path $dist 'Recollect-Windows-x64.zip'
Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $archive -Force
Write-Output "Created $archive"
