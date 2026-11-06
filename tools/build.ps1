param([string]$Python = "python")
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    $version = & $Python -c "from version import VERSION; print(VERSION)"
    if ($LASTEXITCODE -ne 0) { throw 'Could not read version' }
    & $Python tools/version_resource.py build/version-resource.txt
    if ($LASTEXITCODE -ne 0) { throw 'Version resource failed' }
    & $Python -m PyInstaller --noconfirm --clean --onedir --windowed --version-file build/version-resource.txt --distpath "dist/$version/exe" --name KurashiDownloader --collect-all playwright --collect-all pypdfium2 --collect-all pypdfium2_raw launcher.py
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    Copy-Item LICENSE,THIRD_PARTY_NOTICES.md,login-credentials.example.json -Destination "dist/$version/exe/KurashiDownloader"
} finally { Pop-Location }
