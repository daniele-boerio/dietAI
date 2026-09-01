import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AuthProvider } from './AuthContext'
import './index.css'

// Tema applicato prima del render, così non c'è il flash del tema sbagliato al reload.
// Default scuro: è il fondo su cui il disegno è fatto — la carta chiara ci sta
// dentro, sul pasto di adesso e sulla scheda della ricetta, e chi la vuole su
// tutta la pagina la accende dal menu.
document.documentElement.setAttribute(
  'data-theme',
  localStorage.getItem('theme') || 'dark'
)

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
)

// Service worker solo in produzione: in dev darebbe fastidio con la cache di Vite.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}
