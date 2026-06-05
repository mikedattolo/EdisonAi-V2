param(
  [string]$Name,
  [string]$Kind = "bambu",
  [string]$HostAddress = "",
  [string]$Serial = "",
  [string]$AccessCode = "",
  [string]$Slicer = "Bambu Studio",
  [string]$CameraUrl = "",
  [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

if (!$Name) {
  $Name = Read-Host "Printer name"
}
if (!$HostAddress) {
  $HostAddress = Read-Host "Printer LAN IP or hostname"
}
if (!$Serial) {
  $Serial = Read-Host "Printer serial/device id (optional)"
}
if (!$AccessCode) {
  $SecureCode = Read-Host "Printer access code (optional, stored only in local bridge config)" -AsSecureString
  $Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureCode)
  try {
    $AccessCode = [Runtime.InteropServices.Marshal]::PtrToStringAuto($Bstr)
  } finally {
    if ($Bstr -ne [IntPtr]::Zero) {
      [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr)
    }
  }
}

$Body = @{
  name = $Name
  kind = $Kind
  host = $HostAddress
  serial = $Serial
  access_code = $AccessCode
  slicer = $Slicer
  camera_url = $CameraUrl
} | ConvertTo-Json -Depth 6

Invoke-RestMethod `
  -Uri "http://127.0.0.1:$Port/printers/register" `
  -Method Post `
  -ContentType "application/json" `
  -Body $Body |
  ConvertTo-Json -Depth 8
