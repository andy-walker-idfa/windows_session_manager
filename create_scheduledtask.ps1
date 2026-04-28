$path2exe = Read-Host "Enter path to executable file tracker.exe"
$name = "Taskmanager"
$interval = 5

$action = New-ScheduledTaskAction -Execute $path2exe

$trigger = New-ScheduledTaskTrigger -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes $interval) -Once

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal
Start-ScheduledTask -TaskName $name