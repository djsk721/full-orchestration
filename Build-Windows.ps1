param([switch]$InstallBuildDependency)

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if ($InstallBuildDependency) {
        py -3 -m pip install 'pyinstaller>=6,<7' -r requirements-desktop.txt
        if ($LASTEXITCODE -ne 0) { throw 'PyInstaller installation failed.' }
    }
    py -3 -m PyInstaller --noconfirm --onedir --windowed --name ModelOrchestration ModelOrchestration.pyw
    if ($LASTEXITCODE -ne 0) { throw 'Windows build failed.' }
    Write-Host 'Executable: dist\ModelOrchestration\ModelOrchestration.exe'
} finally {
    Pop-Location
}
