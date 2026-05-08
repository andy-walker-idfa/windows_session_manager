$path2exe = Read-Host "Enter path to executable file tracker.exe"
$task_folder = Read-Host "Enter custom folder name in Task Scheduled Library or hit Enter to use default"
$name = "Taskmanager_onetime"


$action = New-ScheduledTaskAction -Execute $path2exe

$trigger = New-ScheduledTaskTrigger -AtStartup

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest

if ($task_folder){
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -TaskPath "\$task_folder\"
} else {
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal
}