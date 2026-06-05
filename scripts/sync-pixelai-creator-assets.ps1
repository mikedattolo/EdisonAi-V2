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

function Get-AssetKind {
  param([string]$Extension)
  $lower = $Extension.ToLowerInvariant()
  if ($lower -eq ".json") { return "workflow" }
  if (@(".safetensors", ".ckpt", ".gguf", ".bin", ".pt", ".pth") -contains $lower) { return "model" }
  if (@(".py", ".bat", ".ps1", ".sh") -contains $lower) { return "script" }
  if (@(".yaml", ".yml", ".toml") -contains $lower) { return "config" }
  if (@(".md", ".txt") -contains $lower) { return "document" }
  return "other"
}

function Copy-RestrictedLabeledAssets {
  param(
    [string]$SourceRoot,
    [string]$DestinationRoot
  )
  $copySuffixes = @(".json", ".yaml", ".yml", ".toml", ".py", ".bat", ".ps1", ".sh", ".md", ".txt")
  $modelSuffixes = @(".safetensors", ".ckpt", ".gguf", ".bin", ".pt", ".pth")
  $mediaSuffixes = @(".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".mp4", ".mov", ".mkv", ".webm", ".avi")
  $restrictedRoot = Join-Path $DestinationRoot "restricted_assets"
  New-Item -ItemType Directory -Force -Path $restrictedRoot | Out-Null

  $candidates = New-Object System.Collections.Generic.List[object]
  Get-ChildItem -LiteralPath $SourceRoot -Recurse -File | Where-Object {
    $_.FullName -match "(?i)nsfw|adult|restricted"
  } | ForEach-Object {
    $extension = $_.Extension.ToLowerInvariant()
    $relative = Get-RelativePath -BasePath $SourceRoot -TargetPath $_.FullName
    $isMedia = $mediaSuffixes -contains $extension
    $isDatasetMediaTree = $_.FullName -match "(?i)\\data\\lena_hub\\nsfw\\" -or $_.FullName -match "(?i)\\NSFW\\"
    $kind = Get-AssetKind -Extension $extension
    $copied = $false

    if (($copySuffixes -contains $extension) -and -not $isMedia -and -not $isDatasetMediaTree) {
      $target = Join-Path $restrictedRoot $relative
      New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
      Copy-Item -LiteralPath $_.FullName -Destination $target -Force
      $copied = $true
    }

    if (($modelSuffixes -contains $extension) -or $copied) {
      $candidates.Add([ordered]@{
        name = $_.Name
        kind = $kind
        source_path = $_.FullName
        relative_path = $relative
        size_bytes = $_.Length
        copied = $copied
      }) | Out-Null
    }
  }
  return $candidates
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
  $OutputPath = Join-Path $env:TEMP ("edison-pixelai-creator-bundle-" + [guid]::NewGuid().ToString("N"))
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

$restrictedCandidates = Copy-RestrictedLabeledAssets -SourceRoot $SourcePath -DestinationRoot $OutputPath

$manifest = @{
  name = "PixelAI Creator Studio Edison bundle"
  created_at = (Get-Date).ToUniversalTime().ToString("o")
  source_path = $SourcePath
  guardrails = @(
    "AI-generated or rights-cleared fictional adult personas only",
    "No nude, pornographic, or sexually explicit output",
    "No real-person likeness, celebrity impersonation, or non-consensual datasets",
    "No minors or youth-coded creator content"
  )
  copied_paths = @("templates", "docs", "config", "restricted_assets", "data/datasets", "data/lena_hub/sfw", "data/lena_hub/training_ready")
  restricted_asset_candidates = $restrictedCandidates
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $OutputPath "edison_creator_bundle_manifest.json") -Encoding UTF8

Write-Host "Prepared Creator Studio bundle at $OutputPath"

if ($Remote) {
  ssh $Remote "mkdir -p '$RemotePath'"
  scp -r (Join-Path $OutputPath "*") "${Remote}:$RemotePath/"
  Write-Host "Synced Creator Studio bundle to ${Remote}:$RemotePath"
}
