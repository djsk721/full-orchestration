param(
    [string]$Executable = (Join-Path $PSScriptRoot 'dist\ModelOrchestration\ModelOrchestration.exe'),
    [switch]$Unregister
)

$ErrorActionPreference = 'Stop'
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$name = 'Model Orchestration Supervisor'
if ($Unregister) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
    return
}
if ($env:ORCHESTRA_DATA) {
    throw 'Scheduled launch expects the default data directory.'
}
$path = (Resolve-Path -LiteralPath $Executable).Path
if ([IO.Path]::GetExtension($path) -ne '.exe') {
    throw 'Specify the built ModelOrchestration.exe.'
}
$action = New-ScheduledTaskAction -Execute $path -Argument '--supervisor' -WorkingDirectory (Split-Path $path)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings
