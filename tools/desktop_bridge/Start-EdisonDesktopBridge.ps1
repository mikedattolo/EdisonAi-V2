param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$ConfigPath = Join-Path $RepoRoot "config\desktop-bridge.local.json"
$ScriptPath = Join-Path $RepoRoot "tools\desktop_bridge\edison_desktop_bridge.py"

if (!(Test-Path $ScriptPath)) {
  throw "Desktop bridge script not found at $ScriptPath"
}

if (!(Test-Path $ConfigPath)) {
  $DiscoveryPath = Join-Path $RepoRoot "config\integration-discovery.local.json"
  $Apps = @{}
  $Printers = @()
  if (Test-Path $DiscoveryPath) {
    $Snapshot = Get-Content $DiscoveryPath -Raw | ConvertFrom-Json
    foreach ($Item in @($Snapshot.paths)) {
      if ($Item.name -and $Item.path) {
        $ToolId = ($Item.name.ToLowerInvariant() -replace '[^a-z0-9]+','-').Trim('-')
        $Apps[$ToolId] = @{
          id = $ToolId
          name = $Item.name
          path = $Item.path
          args = @()
        }
      }
    }
    $Printers = @($Snapshot.printers)
  }
  $Config = @{
    host = "0.0.0.0"
    port = $Port
    allowed_roots = @(
      (Join-Path $RepoRoot "projects"),
      (Join-Path $RepoRoot "artifacts"),
      (Join-Path $env:USERPROFILE "Documents"),
      (Join-Path $env:USERPROFILE "Downloads")
    )
    apps = $Apps
    printers = $Printers
    three_d_printers = @()
    fusion = @{
      queue_dir = (Join-Path $RepoRoot "projects\fusion-jobs\queue")
      results_dir = (Join-Path $RepoRoot "projects\fusion-jobs\results")
      exports_dir = (Join-Path $RepoRoot "projects\fusion-jobs\exports")
      launch_tool_id = ""
    }
    slicer_jobs_dir = (Join-Path $RepoRoot "projects\slicer-jobs")
  }
  $Config | ConvertTo-Json -Depth 8 | Set-Content -Path $ConfigPath -Encoding UTF8
}

$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (!$Python) {
  $Python = (Get-Command py -ErrorAction SilentlyContinue).Source
}
if (!$Python) {
  throw "Python was not found on PATH."
}

$Existing = Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*edison_desktop_bridge.py*" }
foreach ($Process in $Existing) {
  Stop-Process -Id $Process.ProcessId -Force -ErrorAction SilentlyContinue
}

$LogPath = Join-Path $RepoRoot "logs\desktop-bridge.log"
$ErrorLogPath = Join-Path $RepoRoot "logs\desktop-bridge.err.log"
New-Item -ItemType Directory -Force -Path (Split-Path $LogPath) | Out-Null

Start-Process -FilePath $Python `
  -ArgumentList @("`"$ScriptPath`"", "--config", "`"$ConfigPath`"") `
  -WorkingDirectory $RepoRoot `
  -RedirectStandardOutput $LogPath `
  -RedirectStandardError $ErrorLogPath `
  -WindowStyle Hidden

Start-Sleep -Seconds 1
Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 5 | ConvertTo-Json -Depth 8
