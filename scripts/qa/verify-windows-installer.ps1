$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$product = 'Model Orchestration Preview'
$registries = @(
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
if (Get-ItemProperty -Path $registries -ErrorAction SilentlyContinue | Where-Object DisplayName -like "$product*") {
    throw "Use a disposable Windows host without an existing $product installation."
}

$installers = @(Get-ChildItem (Join-Path $root 'apps\desktop\release') -File -Filter '*.exe')
if ($installers.Count -ne 1) { throw 'Expected one NSIS installer from npm run verify -- --ui --package.' }
Write-Host "Installer: $($installers[0].Name) ($($installers[0].Length) bytes)"
Write-Host "SHA256: $((Get-FileHash -LiteralPath $installers[0].FullName).Hash)"
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("orchestra-installer-" + [guid]::NewGuid().ToString('N'))
$target = Join-Path $testRoot 'install'
$data = Join-Path $env:LOCALAPPDATA 'ModelOrchestration'
if (Test-Path -LiteralPath $data) {
    throw 'Use a disposable Windows account without an existing ModelOrchestration data directory.'
}
$dataCreated = $false
$originalExecutable = $env:ORCHESTRA_PREVIEW_EXECUTABLE
$originalInstallerData = $env:ORCHESTRA_INSTALLER_DATA
$python = if ($env:PYTHON) { $env:PYTHON } else { 'python' }

function Install-Preview {
    $setup = Start-Process -FilePath $installers[0].FullName -ArgumentList "/S /D=$target" -PassThru -Wait
    if ($setup.ExitCode -ne 0) { throw "NSIS installation failed ($($setup.ExitCode))." }
    if (-not (Test-Path -LiteralPath $binary -PathType Leaf)) {
        throw 'Installed Electron executable was not found.'
    }
    $runtime = Join-Path (Split-Path $workspace) '_internal'
    if (-not (Test-Path -LiteralPath $workspace -PathType Leaf) -or
        -not (Get-ChildItem -LiteralPath $runtime -Filter 'python3*.dll' -ErrorAction SilentlyContinue |
            Where-Object Name -Match '^python3[0-9]+\.dll$')) {
        throw 'The installed Tk workspace or bundled Python runtime was not found.'
    }
}

function Remove-Preview {
    $uninstaller = @(Get-ChildItem -LiteralPath $target -File -Filter 'Uninstall*.exe')
    if ($uninstaller.Count -ne 1) { throw 'Expected one uninstaller in the temporary install directory.' }
    $cleanup = Start-Process -FilePath $uninstaller[0].FullName -ArgumentList '/S' -PassThru -Wait
    if ($cleanup.ExitCode -ne 0) { throw "NSIS uninstall failed ($($cleanup.ExitCode))." }
    if (Test-Path -LiteralPath $binary -PathType Leaf) { throw 'Installed executable remains after uninstall.' }
    if (Test-Path -LiteralPath $workspace -PathType Leaf) { throw 'Installed workspace remains after uninstall.' }
}

function Assert-DataRetained {
    foreach ($name in $originalHashes.Keys) {
        $path = Join-Path $data $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-FileHash -LiteralPath $path).Hash -ne $originalHashes[$name]) {
            throw "Python user data changed or disappeared: $name"
        }
    }
}

$binary = Join-Path $target 'model-orchestration-preview.exe'
$workspace = Join-Path $target 'resources\workspace\ModelOrchestration.exe'
Push-Location $root
try {
    New-Item -ItemType Directory -Path $data -ErrorAction Stop | Out-Null
    $dataCreated = $true
    & $python 'apps/desktop/tests/legacy_fixture.py' $data '--installer-persistence'
    if ($LASTEXITCODE -ne 0) { throw 'Python failed to create the isolated user-data fixture.' }
    [IO.File]::WriteAllText((Join-Path $data 'ui_prefs.json'), '{"locale":"en","theme":"light"}')
    [IO.File]::WriteAllText((Join-Path $data 'ui-workspace.json'), '{"version":1,"sidebar_hidden":true}')
    $originalHashes = @{}
    foreach ($name in @('state.db', 'registry.json', 'workspace.json', 'ui_prefs.json', 'ui-workspace.json')) {
        $originalHashes[$name] = (Get-FileHash -LiteralPath (Join-Path $data $name)).Hash
    }
    $env:ORCHESTRA_PREVIEW_EXECUTABLE = $binary
    $env:ORCHESTRA_INSTALLER_DATA = $data
    foreach ($stage in @('fresh install', 'reinstall')) {
        Write-Host "Verifying $stage"
        Install-Preview
        & $python 'tests/smoke_packaged_windows_workspace.py' $workspace --open-terminal
        if ($LASTEXITCODE -ne 0) { throw "Installed Tk workspace verification failed after $stage." }
        npm.cmd run test:e2e
        if ($LASTEXITCODE -ne 0) { throw "Installed Electron verification failed after $stage." }
        Assert-DataRetained
        Remove-Preview
        Assert-DataRetained
        Write-Host "PASS: $stage, Tk and Electron startup and shutdown, uninstall and unchanged SQLite/configuration hashes"
    }
} finally {
    $env:ORCHESTRA_PREVIEW_EXECUTABLE = $originalExecutable
    $env:ORCHESTRA_INSTALLER_DATA = $originalInstallerData
    try {
        if (Test-Path -LiteralPath $binary -PathType Leaf) { Remove-Preview }
    } finally {
        Pop-Location
        if (-not (Test-Path -LiteralPath $binary) -and (Test-Path -LiteralPath $testRoot -PathType Container)) {
            Remove-Item -LiteralPath $testRoot -Recurse -Force
        }
        if ($dataCreated -and (Test-Path -LiteralPath $data -PathType Container)) {
            Remove-Item -LiteralPath $data -Recurse -Force
        }
    }
}
