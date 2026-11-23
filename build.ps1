param([string]$Python = "python")

$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    & $Python -m PyInstaller --noconfirm --clean --onefile --windowed `
        --name ClaudeUsageTray `
        --hidden-import pystray._win32 `
        --distpath dist --workpath build --specpath build `
        main.pyw
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
