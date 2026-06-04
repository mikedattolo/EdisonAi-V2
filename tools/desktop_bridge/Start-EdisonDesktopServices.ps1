param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [string]$EdisonHost = "192.168.1.34",
  [string]$EdisonUser = "mike",
  [int]$Port = 8765,
  [int]$MaxTunnelAttempts = 24,
  [int]$RetryDelaySeconds = 5
)

$ErrorActionPreference = "Stop"
$LogPath = Join-Path $RepoRoot "logs\desktop-services-startup.log"
New-Item -ItemType Directory -Force -Path (Split-Path $LogPath) | Out-Null

function Write-StartupLog {
  param([string]$Message)
  $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  "$Timestamp $Message" | Add-Content -Path $LogPath -Encoding UTF8
}

Write-StartupLog "Starting Edison desktop services."

try {
  $ConfigPath = Join-Path $RepoRoot "config\desktop-bridge.local.json"
  $BridgeScript = Join-Path $RepoRoot "tools\desktop_bridge\edison_desktop_bridge.py"
  if (!(Test-Path $BridgeScript)) {
    throw "Desktop bridge script not found at $BridgeScript"
  }

  $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
  if (!$Python) {
    $Python = (Get-Command py -ErrorAction SilentlyContinue).Source
  }
  if (!$Python) {
    throw "Python was not found on PATH."
  }

  $ExistingBridge = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -like "*edison_desktop_bridge.py*" }
  foreach ($Process in $ExistingBridge) {
    Stop-Process -Id $Process.ProcessId -Force -ErrorAction SilentlyContinue
  }

  $BridgeLogPath = Join-Path $RepoRoot "logs\desktop-bridge.log"
  $BridgeErrorLogPath = Join-Path $RepoRoot "logs\desktop-bridge.err.log"
  Start-Process -FilePath $Python `
    -ArgumentList @("`"$BridgeScript`"", "--config", "`"$ConfigPath`"") `
    -WorkingDirectory $RepoRoot `
    -RedirectStandardOutput $BridgeLogPath `
    -RedirectStandardError $BridgeErrorLogPath `
    -WindowStyle Hidden

  $BridgeReady = $false
  for ($Attempt = 1; $Attempt -le 10; $Attempt++) {
    try {
      $Health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3
      if ($Health.ok -eq $true) {
        $BridgeReady = $true
        Write-StartupLog "Desktop bridge started with $($Health.apps.Count) apps and $($Health.printers.Count) printers."
        break
      }
    } catch {
      Write-StartupLog "Desktop bridge health attempt ${Attempt} failed: $($_.Exception.Message)"
      Start-Sleep -Seconds 1
    }
  }
  if (!$BridgeReady) {
    throw "Desktop bridge did not become healthy."
  }
} catch {
  Write-StartupLog "Desktop bridge failed: $($_.Exception.Message)"
  throw
}

$KeyPath = Join-Path $env:USERPROFILE ".ssh\edison_desktop_bridge_tunnel"
if (!(Test-Path $KeyPath)) {
  throw "SSH tunnel key was not found at $KeyPath."
}
$ForwardSpec = "127.0.0.1:$Port`:127.0.0.1:$Port"
$LastError = $null
for ($Attempt = 1; $Attempt -le $MaxTunnelAttempts; $Attempt++) {
  try {
    $ExistingTunnel = Get-CimInstance Win32_Process |
      Where-Object { $_.Name -eq "ssh.exe" -and $_.CommandLine -like "*$ForwardSpec*" }
    foreach ($Process in $ExistingTunnel) {
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
    $TunnelProcess = Get-CimInstance Win32_Process |
      Where-Object { $_.Name -eq "ssh.exe" -and $_.CommandLine -like "*$ForwardSpec*" } |
      Select-Object -First 1
    if (!$TunnelProcess) {
      throw "Tunnel process did not stay running."
    }
    Write-StartupLog "Tunnel started on attempt ${Attempt}: process $($TunnelProcess.ProcessId)."
    Write-StartupLog "Edison desktop services are running."
    exit 0
  } catch {
    $LastError = $_.Exception.Message
    Write-StartupLog "Tunnel attempt ${Attempt} failed: $LastError"
    Start-Sleep -Seconds $RetryDelaySeconds
  }
}

Write-StartupLog "Tunnel failed after $MaxTunnelAttempts attempts: $LastError"
throw "Edison desktop tunnel failed after $MaxTunnelAttempts attempts: $LastError"
