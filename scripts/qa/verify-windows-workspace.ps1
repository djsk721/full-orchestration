param(
    [ValidateSet(96, 120, 144)]
    [int]$ExpectedDpi,
    [string]$ScreenshotDirectory,
    [switch]$WorkspaceOnly,
    [switch]$Benchmark
)

$ErrorActionPreference = 'Stop'
if (-not $IsWindows) {
    [Console]::Error.WriteLine('NOT VERIFIED: use PowerShell 7 on a native Windows interactive desktop.')
    exit 2
}

$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$python = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
$observed = @{ ORCHESTRA_LANG = $env:ORCHESTRA_LANG }
$argsForSmoke = @('tests/smoke_windows_workspace.py')
if ($ExpectedDpi) { $argsForSmoke += @('--expected-dpi', "$ExpectedDpi") }
if ($ScreenshotDirectory) { $argsForSmoke += @('--screenshots', $ScreenshotDirectory) }
if ($Benchmark) { $argsForSmoke += '--benchmark' }

Push-Location $root
try {
    $env:ORCHESTRA_LANG = 'ko'
    & $python @argsForSmoke
    if ($LASTEXITCODE -ne 0) { throw 'Native Windows workspace validation failed.' }
    if (-not $WorkspaceOnly) {
        npm.cmd run verify -- --ui --package
        if ($LASTEXITCODE -ne 0) { throw 'Shared Windows regression or packaging failed.' }
        & (Join-Path $PSScriptRoot 'verify-windows-installer.ps1')
    }
} finally {
    $env:ORCHESTRA_LANG = $observed.ORCHESTRA_LANG
    Pop-Location
}
