# Creates 4 Windows scheduled tasks, one per life-agent task at its intended time.
# Run as Administrator:
#   Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
#   .\setup_scheduler.ps1
#
# Times are LOCAL time (your PC is on IST, matching the design).

$ProjectPath = "D:\life-agent"
$Runner = Join-Path $ProjectPath "run_task.bat"

$Schedule = @(
    @{ Task = "meal_plan";        Time = "07:00" },
    @{ Task = "ai_edge";          Time = "08:00" },
    @{ Task = "evening_checkin";  Time = "21:30" },
    @{ Task = "goal_planner";     Time = "21:45" },
    @{ Task = "tomorrow_planner"; Time = "22:00" },
    @{ Task = "set_reminders";    Time = "22:15" }
)

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

foreach ($item in $Schedule) {
    $name = "life-agent-$($item.Task)"
    $trigger = New-ScheduledTaskTrigger -Daily -At $item.Time
    $action = New-ScheduledTaskAction -Execute $Runner -Argument $item.Task -WorkingDirectory $ProjectPath
    try {
        Register-ScheduledTask -TaskName $name -Trigger $trigger -Action $action `
            -Settings $settings -Description "life-agent $($item.Task) daily at $($item.Time)" -Force | Out-Null
        Write-Host "[OK] $name -> daily at $($item.Time)"
    }
    catch {
        Write-Host "[FAIL] $name : $_"
    }
}

Write-Host ""
Write-Host "Verify:  Get-ScheduledTask -TaskName 'life-agent-*'"
Write-Host "Test now:  Start-ScheduledTask -TaskName 'life-agent-evening_checkin'"
Write-Host "Logs:  $ProjectPath\logs\"
Write-Host ""
Write-Host "NOTE: 'StartWhenAvailable' is on — if the PC was asleep/off at the"
Write-Host "trigger time, the task runs as soon as it's back on."
Write-Host ""
Write-Host "Remove all:  Unregister-ScheduledTask -TaskName 'life-agent-*' -Confirm:`$false"
