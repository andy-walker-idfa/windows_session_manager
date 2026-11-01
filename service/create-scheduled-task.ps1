#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Creates (or removes) the scheduled task that runs the Time Manager tracker on Windows.
.DESCRIPTION
  Optional: the same task can be created by hand in Task Scheduler (see README.md, "Windows:
  scheduled task"). This script uses exactly those settings:
    - runs tracker.exe as SYSTEM with highest privileges, at startup, no repetition
    - no execution time limit; restart every minute if it fails (up to 999 times)
    - one instance only; runs on battery; does not wake the computer
  Run it from the install folder (C:\Program Files\TimeManager), in PowerShell as administrator.
.PARAMETER TrackerPath
  The tracker program. Default: tracker\tracker.exe next to this script.
.PARAMETER TaskName
  Name of the task. Default: TimeManagerTracker.
.PARAMETER TaskFolder
  Optional Task Scheduler folder, for example "My" for \My\TimeManagerTracker.
.PARAMETER Remove
  Stop and delete the task instead of creating it.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\create-scheduled-task.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\create-scheduled-task.ps1 -Remove
#>
param(
    [string]$TrackerPath = (Join-Path $PSScriptRoot "tracker\tracker.exe"),
    [string]$TaskName = "TimeManagerTracker",
    [string]$TaskFolder = "",
    [switch]$Remove
)
$ErrorActionPreference = "Stop"
$taskPath = if ($TaskFolder) { "\$($TaskFolder.Trim('\'))\" } else { "\" }
$existing = Get-ScheduledTask -TaskName $TaskName -TaskPath $taskPath -ErrorAction SilentlyContinue

if ($Remove) {
    if (-not $existing) {
        Write-Host "No task '$taskPath$TaskName' found; nothing to remove."
        exit 0
    }
    Stop-ScheduledTask -TaskName $TaskName -TaskPath $taskPath -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -TaskPath $taskPath -Confirm:$false
    Write-Host "Removed task '$taskPath$TaskName'. The program files in $PSScriptRoot are unchanged."
    exit 0
}

if (-not (Test-Path $TrackerPath -PathType Leaf)) {
    Write-Host "Tracker not found: $TrackerPath"
    Write-Host "Run this script from the install folder (e.g. C:\Program Files\TimeManager), or give -TrackerPath."
    exit 1
}
$TrackerPath = (Resolve-Path $TrackerPath).Path

if ($existing) {
    # Replace it, so that a changed path or older settings are updated.
    Stop-ScheduledTask -TaskName $TaskName -TaskPath $taskPath -ErrorAction SilentlyContinue
    Write-Host "Task '$taskPath$TaskName' exists; replacing it."
}

$action = New-ScheduledTaskAction -Execute $TrackerPath
$trigger = New-ScheduledTaskTrigger -AtStartup
# No time limit (the tracker runs as one long loop), restart on failure, a single instance,
# and keep running on battery (laptops).
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -TaskPath $taskPath -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Time Manager tracker: enforces daily time limits and allowed login hours." -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName -TaskPath $taskPath

Write-Host "Created and started task '$taskPath$TaskName'."
Write-Host "  Program: $TrackerPath"
Write-Host "  Runs as SYSTEM at startup; restarts on failure; no time limit."
Write-Host "Log: $(Join-Path (Split-Path (Split-Path $TrackerPath)) 'logs\tracker.log')"
