$path2exe = Read-Host "Enter path to executable file tracker.exe"
$task_folder = Read-Host "Enter custom folder name in Task Scheduled Library or hit Enter to use default"
$name = "Taskmanager_onetime"


$action = New-ScheduledTaskAction -Execute $path2exe

$trigger = New-ScheduledTaskTrigger -AtStartup

#ExecutionTimeLimit of zero means no limit. The tracker is a long running loop started only at
#system startup, so the default 72 hour limit would have the Task Scheduler kill it with nothing
#to start it again until the next reboot.
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest

if ($task_folder){
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -TaskPath "\$task_folder\"
} else {
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal
}