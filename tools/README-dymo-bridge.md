# DYMO LabelWriter 5XL print bridge (Windows)

The 5XL is a 550-series printer with a closed protocol that has no working Linux
driver, so Edison cannot print to it directly. `dymo_bridge.py` runs on the Windows
PC that has DYMO Connect installed and forwards Edison print requests to DYMO
Connect.s local Web Service (DWS, https://127.0.0.1:41951), which drives the 5XL.

- Edison service: `apps/api/edison_core/services/label_printer.py` POSTs a rendered
  PNG to the bridge (`EDISON_DYMO_BRIDGE_URL`, default http://192.168.1.31:8088).
- Bridge endpoints: `GET /status`, `POST /print {image_base64, copies}`.
- Auto-start: Startup-folder VBS launches it hidden at logon; a keepalive polls DWS
  every 45s to keep the printer ready.
- Firewall: inbound TCP 8088 must be allowed (one-time admin).
