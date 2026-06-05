# Edison Desktop Bridge

Runs on the main Windows PC so Edison can use allowlisted desktop tools without
putting secrets or broad filesystem access in the repo.

## Start

```powershell
powershell -ExecutionPolicy Bypass -File tools\desktop_bridge\Start-EdisonDesktopBridge.ps1
powershell -ExecutionPolicy Bypass -File tools\desktop_bridge\Start-EdisonBridgeTunnel.ps1
```

The helper creates `config/desktop-bridge.local.json` from the local integration
scan, starts `edison_desktop_bridge.py` on port `8765`, and verifies `/health`.
The tunnel helper exposes the bridge privately to Edison as
`http://127.0.0.1:8765` on the Edison machine, avoiding a Windows Firewall LAN
port rule.

## Start At Windows Login

```powershell
powershell -ExecutionPolicy Bypass -File tools\desktop_bridge\Register-EdisonDesktopStartup.ps1
```

This registers a current-user scheduled task named `Edison Desktop Services`.
It runs `Start-EdisonDesktopServices.ps1`, which starts the bridge first, then
retries the Edison SSH tunnel while the network is still coming online.

## Endpoints

- `GET /health` lists allowlisted apps, printers, and file roots.
- `GET /tools` lists bridge capabilities and allowlisted apps.
- `GET /printers` lists Windows printers, configured 3D printers, and slicer tools.
- `POST /launch` launches an allowlisted app by `tool_id`.
- `POST /notify` shows a desktop notification.
- `POST /print-label` sends an allowed local label path to Windows printing.
- `POST /files/list` lists a folder inside an allowlisted root.
- `POST /files/read` reads a text file inside an allowlisted root.
- `POST /files/write` writes a text file inside an allowlisted root.
- `POST /files/mkdir` creates a folder inside an allowlisted root.
- `POST /fusion/job` queues a Fusion 360 automation job for the Fusion add-in.
- `POST /slicer/open` opens an STL/3MF/OBJ path in Bambu Studio, OrcaSlicer, or Cura.
- `POST /slicer/prepare` creates a print-production handoff manifest.
- `POST /printers/register` saves a 3D printer profile in the ignored local config.

The local config file is ignored by git. Keep API keys, Shopify tokens, phone
numbers, and printer-specific secrets there or in environment variables, not in
source control.

## Register A 3D Printer

Start the bridge, then run:

```powershell
powershell -ExecutionPolicy Bypass -File tools\desktop_bridge\Register-Edison3DPrinter.ps1 `
  -Name "Bambu A1" `
  -Kind bambu `
  -HostAddress "192.168.1.50" `
  -Serial "YOUR-PRINTER-SERIAL" `
  -Slicer "Bambu Studio"
```

The access code prompt is optional and writes only to
`config/desktop-bridge.local.json`, which is ignored by git. Edison can already
see the profile through `GET /api/v1/desktop-bridge/printers`. Direct LAN
printer control can be layered on once each printer has its LAN IP, serial/device
ID, and access code registered; until then Edison hands print jobs to the
installed slicer apps on the PC.

## Fusion 360 Control

The bridge queues CAD jobs in `projects\fusion-jobs\queue`. Fusion itself needs
to run the Fusion API, so install the add-in once:

1. Open Fusion 360 on the main PC.
2. Go to `Utilities` > `Scripts and Add-Ins`.
3. Add this folder:
   `tools\desktop_bridge\fusion_addin\EdisonFusionBridge`.
4. Run `EdisonFusionBridge`; enable run-at-startup in Fusion if you want it
   always listening.

Edison can then call `POST /api/v1/desktop-bridge/fusion/job`. The bridge writes
a job JSON file, launches Fusion 360 if requested, and the add-in writes results
to `projects\fusion-jobs\results` and exports to `projects\fusion-jobs\exports`.

Example Fusion test job:

```powershell
$Body = @{
  launch = $false
  prompt = "Create a simple 40 x 30 x 12 mm block"
  parameters = @{ command = "box"; width_mm = 40; depth_mm = 30; height_mm = 12 }
  exports = @(@{ name = "test-block"; format = "stl" })
} | ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri "http://127.0.0.1:8765/fusion/job" -Method Post -ContentType "application/json" -Body $Body
```
