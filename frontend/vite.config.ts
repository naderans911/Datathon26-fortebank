import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backend = {
  target: process.env.VITE_API_PROXY || 'http://127.0.0.1:8000',
  changeOrigin: false,
}

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': backend,
      '/docs': backend,
      '/openapi.json': backend,
    },
  },
})
