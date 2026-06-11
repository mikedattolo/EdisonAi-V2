import fs from 'node:fs';

import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Serve over HTTPS when a self-signed cert is present (apps/web/certs/).
// A secure origin is required for the browser microphone (voice mode + wake word).
function httpsOptions() {
  try {
    return {
      key: fs.readFileSync(new URL('./certs/key.pem', import.meta.url)),
      cert: fs.readFileSync(new URL('./certs/cert.pem', import.meta.url)),
    };
  } catch {
    return undefined;
  }
}

const proxy = {
  '/api': 'http://127.0.0.1:8000',
  '/health': 'http://127.0.0.1:8000',
};

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: true,
    port: 5173,
    https: httpsOptions(),
    proxy,
  },
  preview: {
    allowedHosts: true,
    port: 5173,
    https: httpsOptions(),
    proxy,
  },
});
