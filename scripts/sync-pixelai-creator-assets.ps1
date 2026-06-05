param(
  [string]$SourcePath = "F:\pixelaiLabs_ComfyUI_Installer_08-19-25\pixelaiLabs_ComfyUI_Installer",
  [string]$OutputPath = "",
  [string]$Remote = "",
  [string]$RemotePath = "/home/mike/EdisonAi-V2/vendor/pixelai_creator_studio"
)

$ErrorActionPreference = "Stop"

function Copy-SafeTree {
  param(
    [string]$Source,
    [string]$Destination
  )
  if (-not (Test-Path -LiteralPath $Source)) {
    return
  }
  Get-ChildItem -LiteralPath $Source -Recurse -File | Where-Object {
    $_.FullName -notmatch "\\(nsfw|adult|restricted|porn|explicit)[^\\]*\\"
  } | ForEach-Object {
    $relative = Get-RelativePath -BasePath $Source -TargetPath $_.FullName
    $target = Join-Path $Destination $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $target -Force
  }
}

function Get-RelativePath {
  param(
    [string]$BasePath,
    [string]$TargetPath
  )
  $baseFullPath = [System.IO.Path]::GetFullPath($BasePath)
  if (-not $baseFullPath.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
    $baseFullPath += [System.IO.Path]::DirectorySeparatorChar
  }
  $baseUri = New-Object System.Uri($baseFullPath)
  $targetUri = New-Object System.Uri([System.IO.Path]::GetFullPath($TargetPath))
  return [System.Uri]::UnescapeDataString($baseUri.MakeRelativeUri($targetUri).ToString()).Replace('/', [System.IO.Path]::DirectorySeparatorChar)
}

$creatorRoot = Join-Path $SourcePath "creator_studio"
if (-not (Test-Path -LiteralPath $creatorRoot)) {
  if ((Split-Path -Leaf $SourcePath) -eq "creator_studio") {
    $creatorRoot = $SourcePath
  } else {
    throw "Could not find creator_studio under $SourcePath"
  }
}

if (-not $OutputPath) {
  $OutputPath = Join-Path $env:TEMP ("edison-pixelai-creator-safe-" + [guid]::NewGuid().ToString("N"))
}

New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null

Copy-SafeTree -Source (Join-Path $creatorRoot "templates") -Destination (Join-Path $OutputPath "templates")
Copy-SafeTree -Source (Join-Path $creatorRoot "docs") -Destination (Join-Path $OutputPath "docs")

$configTarget = Join-Path $OutputPath "config"
New-Item -ItemType Directory -Force -Path $configTarget | Out-Null
foreach ($fileName in @("creator_studio_config.yaml", "comfyui_workflow_registry.yaml")) {
  $sourceFile = Join-Path (Join-Path $creatorRoot "config") $fileName
  if (Test-Path -LiteralPath $sourceFile) {
    Copy-Item -LiteralPath $sourceFile -Destination (Join-Path $configTarget $fileName) -Force
  }
}

foreach ($folder in @("data\datasets", "data\lena_hub\sfw", "data\lena_hub\training_ready")) {
  New-Item -ItemType Directory -Force -Path (Join-Path $OutputPath $folder) | Out-Null
}

$manifest = @{
  name = "PixelAI Creator Studio safe Edison bundle"
  created_at = (Get-Date).ToUniversalTime().ToString("o")
  source_path = $SourcePath
  guardrails = @(
    "AI-generated or rights-cleared fictional adult personas only",
    "No nude, pornographic, or sexually explicit output",
    "No real-person likeness, celebrity impersonation, or non-consensual datasets",
    "No minors or youth-coded creator content"
  )
  copied_paths = @("templates", "docs", "config", "data/datasets", "data/lena_hub/sfw", "data/lena_hub/training_ready")
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $OutputPath "edison_creator_bundle_manifest.json") -Encoding UTF8

Write-Host "Prepared safe Creator Studio bundle at $OutputPath"

if ($Remote) {
  ssh $Remote "mkdir -p '$RemotePath'"
  scp -r (Join-Path $OutputPath "*") "${Remote}:$RemotePath/"
  Write-Host "Synced Creator Studio bundle to ${Remote}:$RemotePath"
}
