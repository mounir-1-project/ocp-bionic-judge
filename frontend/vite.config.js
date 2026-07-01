import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // All API routes proxied to FastAPI — cookies are forwarded automatically
      // because the browser sees requests going to the same origin (localhost:5173).
      '/api':               { target: 'http://localhost:8000', changeOrigin: true },
      '/auth':              { target: 'http://localhost:8000', changeOrigin: true },
      '/decisions':         { target: 'http://localhost:8000', changeOrigin: true },
      '/governance-metrics':{ target: 'http://localhost:8000', changeOrigin: true },
      '/health':            { target: 'http://localhost:8000', changeOrigin: true },
      '/analyze':           { target: 'http://localhost:8000', changeOrigin: true },
      '/openapi.json':      { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
