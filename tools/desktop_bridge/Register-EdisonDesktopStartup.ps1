param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [string]$TaskName = "Edison Desktop Services",
  [string]$EdisonHost = "192.168.1.34",
  [string]$EdisonUser = "mike",
  [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$StartupScript = Join-Path $RepoRoot "tools\desktop_bridge\Start-EdisonDesktopServices.ps1"

if (!(Test-Path $StartupScript)) {
  throw "Startup script not found at $StartupScript"
}

$ActionArgs = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", "`"$StartupScript`"",
  "-RepoRoot", "`"$RepoRoot`"",
  "-EdisonHost", "`"$EdisonHost`"",
  "-EdisonUser", "`"$EdisonUser`"",
  "-Port", $Port
) -join " "

$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $ActionArgs
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$Settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
  -MultipleInstances IgnoreNew `
  -RestartCount 3 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -StartWhenAvailable
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $Action `
  -Trigger $Trigger `
  -Settings $Settings `
  -Principal $Principal `
  -Description "Starts the Edison main-PC desktop bridge and SSH reverse tunnel at Windows login." `
  -Force | Out-Null

Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName,State,TaskPath | ConvertTo-Json
