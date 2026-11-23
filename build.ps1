param(
    [string]$Python = "python",
    [string]$Version = "0.0.0"
)

$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    & $Python -m PyInstaller --noconfirm --clean --onedir --windowed `
        --name ClaudeUsageTray `
        --hidden-import pystray._win32 `
        --distpath dist --workpath build --specpath build `
        main.pyw
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $iscc = @(
        (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source,
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $iscc) { throw "ISCC.exe from Inno Setup 6 was not found" }
    & $iscc "/DAppVersion=$Version" installer.iss
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
