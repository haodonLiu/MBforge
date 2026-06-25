import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { readFileSync } from 'node:fs'

// Read version from package.json (kept in sync with constants.yaml by
// scripts/generate_constants.py). Resolved at config load time so the
// value is baked into the build via Vite's `define`.
const pkg = JSON.parse(
  readFileSync(path.resolve(__dirname, 'package.json'), 'utf-8'),
)

export default defineConfig({
  plugins: [react()],
  define: {
    'process.env': {},
    'process': '({env:{}})',
    global: 'globalThis',
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:18792',
        changeOrigin: true,
      },
    },
  },
})
