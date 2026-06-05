param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [string]$AddInRoot = (Join-Path $env:APPDATA "Autodesk\Autodesk Fusion 360\API\AddIns\EdisonFusionBridge")
)

$ErrorActionPreference = "Stop"

$Source = Join-Path $RepoRoot "tools\desktop_bridge\fusion_addin\EdisonFusionBridge"
if (!(Test-Path -LiteralPath $Source)) {
  throw "Fusion add-in source was not found at $Source"
}

New-Item -ItemType Directory -Force -Path $AddInRoot | Out-Null
Copy-Item -Path (Join-Path $Source "*") -Destination $AddInRoot -Recurse -Force

$QueueDir = Join-Path $RepoRoot "projects\fusion-jobs\queue"
$ResultsDir = Join-Path $RepoRoot "projects\fusion-jobs\results"
$ExportsDir = Join-Path $RepoRoot "projects\fusion-jobs\exports"
New-Item -ItemType Directory -Force -Path $QueueDir, $ResultsDir, $ExportsDir | Out-Null

[Environment]::SetEnvironmentVariable("EDISON_FUSION_QUEUE_DIR", $QueueDir, "User")
[Environment]::SetEnvironmentVariable("EDISON_FUSION_RESULTS_DIR", $ResultsDir, "User")
[Environment]::SetEnvironmentVariable("EDISON_FUSION_EXPORTS_DIR", $ExportsDir, "User")

@{
  ok = $true
  add_in_root = $AddInRoot
  queue_dir = $QueueDir
  results_dir = $ResultsDir
  exports_dir = $ExportsDir
  detail = "Edison Fusion Bridge add-in installed. Restart Fusion 360 or run EdisonFusionBridge from Scripts and Add-Ins."
} | ConvertTo-Json -Depth 4
