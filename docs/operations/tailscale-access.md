# Tailscale Access Plan

## Goal

EDISON should be reachable from anywhere the user is signed into their private tailnet, without exposing the AI workstation directly to the public internet.

## Recommended Setup

1. Install Tailscale on the primary Edison AI PC.
2. Sign in to the same tailnet used by the user's laptop and mobile devices.
3. Run the EDISON API and web app on the primary PC, bound to the private host interface or localhost behind a reverse proxy.
4. Use a stable tailnet name such as `edison-v2` through MagicDNS.
5. Put a local reverse proxy, such as Caddy or Traefik, in front of the app for a single private URL.

## Access Shape

- Preferred private URL: `https://edison-v2.<tailnet-name>.ts.net`
- Web UI: reverse-proxy to the frontend service.
- API: reverse-proxy `/api` to FastAPI.
- Optional model/admin endpoints: keep private and require explicit settings toggles.

## Security Rules

- Prefer Tailscale private access over public port forwarding.
- Do not enable Tailscale Funnel for EDISON by default.
- Keep destructive tools behind Edison approval gates even on the tailnet.
- Store secrets in environment variables or local secret storage, never in the repository.
- Require a separate API token for remote worker nodes.

## Future App Settings

The Settings view should eventually manage:

- Tailnet host name.
- Public access disabled/enabled status.
- API bind host and port.
- Reverse proxy health.
- Remote node enrollment tokens.
- Allowed workspace roots.