import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Il backend a cui puntare in sviluppo:
//   - default: quello locale su :8000
//   - server: metti VITE_API_TARGET=https://dietai.spassocasa.it in frontend/.env.local
//
// Il proxy tiene tutto same-origin anche in dev (il browser vede solo localhost:3000):
// è ciò che permette ai cookie httpOnly di funzionare senza CORS e senza token in
// localStorage, esattamente come in produzione dietro Nginx.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_API_TARGET || 'http://localhost:8000'

  console.log(`\n  API → ${target}\n`)

  return {
    plugins: [react()],
    server: {
      port: 3000,
      proxy: {
        '/api': {
          target,
          changeOrigin: true,
          // Il backend in produzione emette cookie Secure senza Domain. Togliere
          // comunque l'attributo Domain evita che un COOKIE_DOMAIN impostato sul
          // server renda i cookie inaccettabili su localhost.
          cookieDomainRewrite: '',
          // Generare una settimana può richiedere minuti: il default di undici
          // secondi taglierebbe la richiesta a metà.
          timeout: 600000,
          proxyTimeout: 600000,
        },
      },
    },
  }
})
