# Shopify To ToyBox3D Setup

Last checked against Shopify docs on 2026-06-05.

Edison currently has the local pieces for a Shopify-to-print workflow:

- ToyBox3D order, mapping, printer, and queue records in the Edison API.
- Desktop bridge handoff to Fusion 360, Bambu Studio, OrcaSlicer, Cura, and DYMO/Windows printing.
- Local settings for store URL, default slicer, label printer name, and notification behavior.

The safest first version is polling: Edison reads recent unfulfilled orders, maps SKUs to print assets, queues slicer/Fusion jobs, and prints label files after labels are created or downloaded. Shopify webhooks can be added after Edison has a public HTTPS URL or tunnel.

## 1. Create A Shopify Custom App

In Shopify Admin:

1. Open `Settings` > `Apps and sales channels` > `Develop apps`.
2. Create an app named `Edison ToyBox3D`.
3. Configure Admin API scopes.
4. Install the app and copy the Admin API access token once.

Store the token only in local secret storage or an environment variable such as:

```powershell
setx EDISON_SHOPIFY_ADMIN_TOKEN "shpat_..."
setx EDISON_SHOPIFY_STORE "your-store.myshopify.com"
```

Do not paste the token into Git, docs, screenshots, or chat logs.

Official references:

- Shopify custom app access tokens: https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens/generate-app-access-tokens-admin
- Shopify access scopes: https://shopify.dev/docs/admin-api/access-scopes

## 2. Suggested Minimum Scopes

Start with only the scopes Edison actually needs:

- `read_orders` for recent order intake.
- `read_products` for SKU, variant, and product mapping.
- `read_locations` if you want to route jobs by Shopify location.
- Fulfillment-order scopes only when Edison is allowed to update fulfillment state.
- `read_all_orders` only if you need orders older than Shopify's default recent-order window and your store/app is approved for it.

For shipping/rate tooling, review Shopify's current `shipping` access scopes before enabling anything. Keep label purchasing and carrier account actions manual until the exact carrier/label API path is chosen.

## 3. Connect Edison Runtime Settings

Set the visible non-secret settings from Edison Settings or the API:

```powershell
Invoke-RestMethod `
  -Uri "http://192.168.1.34:8000/api/v1/toybox/setup/defaults" `
  -Method Post `
  -ContentType "application/json" `
  -Body (@{
    desktop_bridge_url = "http://127.0.0.1:8765"
    shopify_store_url = "https://your-store.myshopify.com"
    dymo_printer_name = "Mike's shipping label printer"
    default_slicer = "Bambu Studio"
  } | ConvertTo-Json -Depth 8)
```

The Admin API token should remain in the Edison service environment, not in the runtime settings JSON. Runtime settings intentionally redact token-like fields.

## 4. Orders To Print Jobs

Use this mapping flow:

1. Create a ToyBox3D product mapping for each Shopify SKU.
2. Set the `model_path`, `slicer_profile`, material, color, and default printer.
3. When an order arrives, Edison creates a ToyBox3D order record.
4. Edison creates queue items for each mapped line item.
5. Edison calls the desktop bridge:
   - `POST /api/v1/desktop-bridge/fusion/job` for parametric CAD/STL generation.
   - `POST /api/v1/desktop-bridge/slicer/prepare` for slicer handoff.
   - `POST /api/v1/desktop-bridge/labels/print` once a label PDF/PNG exists.

## 5. Webhooks Later

Polling is easiest on a private LAN. Webhooks need Shopify to reach Edison over HTTPS. When you are ready for webhooks:

1. Put Edison behind a stable HTTPS endpoint, such as a reverse proxy or tunnel.
2. Add a webhook receiver endpoint to Edison.
3. Subscribe the custom app to order topics using Shopify's GraphQL Admin API.

Useful topics for the future receiver:

- `ORDERS_CREATE`
- `ORDERS_PAID`
- `ORDERS_UPDATED`

Official references:

- Shopify webhook subscriptions: https://shopify.dev/docs/apps/build/webhooks/subscribe
- `webhookSubscriptionCreate`: https://shopify.dev/docs/api/admin-graphql/latest/mutations/webhookSubscriptionCreate

## 6. Shipping Labels

Edison can already print a local label file through the PC desktop bridge and DYMO/Windows printing. The missing decision is where labels are created:

- Shopify Admin / Shopify Shipping: create or buy the label in Shopify, download the PDF/PNG, then let Edison print it.
- Carrier or shipping platform API: use Shippo, EasyPost, Pirate Ship, ShipStation, UPS, USPS, FedEx, or another provider, then Edison downloads and prints the returned label.
- Future Shopify automation: add only after verifying the current supported API path and store eligibility.

Official Shopify Shipping overview: https://help.shopify.com/en/manual/fulfillment/shopify-shipping
