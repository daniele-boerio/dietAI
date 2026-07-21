import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      // Same-origin anche in sviluppo: è ciò che permette ai cookie httpOnly di
      // funzionare senza CORS e senza token in localStorage.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
