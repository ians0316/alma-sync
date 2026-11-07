# Installs the Alma sync as an hourly Windows scheduled task for the current user.
# Run from PowerShell in the repo folder:
#     powershell -ExecutionPolicy Bypass -File .\windows\install_schedule.ps1
$ErrorActionPreference = "Stop"

$TaskName = "Alma Sync"
$WindowsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SyncDir = Join-Path (Split-Path -Parent $WindowsDir) "alma_sync"
if (-not (Test-Path "$SyncDir\sync.py")) { throw "Could not find $SyncDir\sync.py. Keep the windows and alma_sync folders next to each other." }
$AppDir = Join-Path $HOME ".alma_sync"

$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) { throw "Python was not found. Install it from python.org and tick 'Add python.exe to PATH'." }
if ($Python -like "*\WindowsApps\*") { throw "This is the Microsoft Store placeholder for Python, not real Python. Install it from python.org." }

# pythonw.exe runs without opening a console window every hour.
$Pythonw = Join-Path (Split-Path $Python) "pythonw.exe"
if (-not (Test-Path $Pythonw)) { $Pythonw = $Python }

New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$SyncDir\sync.py`"" -WorkingDirectory $SyncDir

# 5 minutes past every hour, starting with the next one, plus once at sign-in.
$Now = Get-Date
$Start = $Now.Date.AddHours($Now.Hour).AddMinutes(5)
if ($Start -le $Now) { $Start = $Start.AddHours(1) }
$Hourly = New-ScheduledTaskTrigger -Once -At $Start -RepetitionInterval (New-TimeSpan -Hours 1)
$AtLogOn = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"

# StartWhenAvailable catches up on runs missed while the PC was asleep or off.
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger @($Hourly, $AtLogOn) -Settings $Settings `
    -Description "Syncs Alma assignments and grades to Notion, Google Calendar, and Google Sheets." -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Installed the '$TaskName' scheduled task. It is running now and then 5 minutes past every hour."
Write-Host "Logs: $AppDir\sync.log"
Write-Host ""
Write-Host "To uninstall: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
