import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./core/frontend"),
      "@campaigns": path.resolve(__dirname, "./campaigns/frontend"),
      "@accounts": path.resolve(__dirname, "./accounts/frontend"),
      "@dashboard": path.resolve(__dirname, "./dashboard/frontend"),
      "@leads": path.resolve(__dirname, "./leads/frontend"),
      "@inbox": path.resolve(__dirname, "./inbox/frontend"),
      "@knowledge": path.resolve(__dirname, "./knowledge/frontend"),
      "@admin": path.resolve(__dirname, "./admin/frontend"),
      "@integrations": path.resolve(__dirname, "./integrations/frontend"),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        proxyTimeout: 30000,
        timeout: 30000,
        configure: (proxy) => {
          proxy.on('error', (err, _req, res) => {
            console.error('[Vite Proxy] Backend unreachable:', err.message)
            // @ts-ignore
            if (!res.headersSent) {
              (res as any).writeHead(503, { 'Content-Type': 'application/json' })
              ;(res as any).end(JSON.stringify({
                error: {
                  code: 'BACKEND_UNAVAILABLE',
                  message: 'Backend server is not running. Start the full dev environment with: ./dev.sh from the repo root'
                }
              }))
            }
          })
        },
      },
    },
  },
})
