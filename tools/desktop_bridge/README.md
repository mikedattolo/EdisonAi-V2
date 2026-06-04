# Edison Desktop Bridge

Runs on the main Windows PC so Edison can use allowlisted desktop tools without
putting secrets or broad filesystem access in the repo.

## Start

```powershell
powershell -ExecutionPolicy Bypass -File tools\desktop_bridge\Start-EdisonDesktopBridge.ps1
```

The helper creates `config/desktop-bridge.local.json` from the local integration
scan, starts `edison_desktop_bridge.py` on port `8765`, and verifies `/health`.

## Endpoints

- `GET /health` lists allowlisted apps, printers, and file roots.
- `POST /launch` launches an allowlisted app by `tool_id`.
- `POST /notify` shows a desktop notification.
- `POST /print-label` sends an allowed local label path to Windows printing.

The local config file is ignored by git. Keep API keys, Shopify tokens, phone
numbers, and printer-specific secrets there or in environment variables, not in
source control.
