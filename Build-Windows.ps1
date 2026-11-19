param(
    [switch]$InstallBuildDependency,
    [switch]$VerifyWorkspace,
    [string]$Python
)

$ErrorActionPreference = 'Stop'
$pythonArgs = @()
if (-not $Python) {
    $Python = 'py'
    $pythonArgs = @('-3')
}
Push-Location $PSScriptRoot
try {
    if ($InstallBuildDependency) {
        & $Python @pythonArgs -m pip install 'pyinstaller>=6,<7' -r requirements-desktop.txt
        if ($LASTEXITCODE -ne 0) { throw 'PyInstaller installation failed.' }
    }
    & $Python @pythonArgs -m PyInstaller --noconfirm --onedir --windowed --name ModelOrchestration ModelOrchestration.pyw
    if ($LASTEXITCODE -ne 0) { throw 'Windows build failed.' }
    $binary = 'dist\ModelOrchestration\ModelOrchestration.exe'
    Write-Host "Executable: $binary"
    if ($VerifyWorkspace) {
        & $Python @pythonArgs 'tests/smoke_packaged_windows_workspace.py' $binary
        if ($LASTEXITCODE -ne 0) { throw 'Packaged Tk workspace verification failed.' }
    }
} finally {
    Pop-Location
}
