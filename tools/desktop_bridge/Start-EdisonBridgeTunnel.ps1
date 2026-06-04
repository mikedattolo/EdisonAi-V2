param(
  [string]$EdisonHost = "192.168.1.34",
  [string]$EdisonUser = "mike",
  [string]$KeyPath = (Join-Path $env:USERPROFILE ".ssh\edison_desktop_bridge_tunnel"),
  [int]$LocalPort = 8765,
  [int]$RemotePort = 8765
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $KeyPath)) {
  throw "SSH tunnel key was not found at $KeyPath. Generate/install it once before starting the tunnel."
}

$ForwardSpec = "127.0.0.1:$RemotePort`:127.0.0.1:$LocalPort"
$Existing = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -eq "ssh.exe" -and $_.CommandLine -like "*$ForwardSpec*" }
foreach ($Process in $Existing) {
  Stop-Process -Id $Process.ProcessId -Force -ErrorAction SilentlyContinue
}

Start-Process -FilePath "ssh.exe" -ArgumentList @(
  "-N",
  "-o", "ExitOnForwardFailure=yes",
  "-o", "ServerAliveInterval=30",
  "-o", "ServerAliveCountMax=3",
  "-o", "StrictHostKeyChecking=accept-new",
  "-i", $KeyPath,
  "-R", $ForwardSpec,
  "$EdisonUser@$EdisonHost"
) -WindowStyle Hidden

Start-Sleep -Seconds 2
$Process = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -eq "ssh.exe" -and $_.CommandLine -like "*$ForwardSpec*" } |
  Select-Object -First 1

if (!$Process) {
  throw "Tunnel process did not stay running."
}

[PSCustomObject]@{
  status = "running"
  process_id = $Process.ProcessId
  edison_url = "http://127.0.0.1:$RemotePort"
  local_url = "http://127.0.0.1:$LocalPort"
} | ConvertTo-Json
