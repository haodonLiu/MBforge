import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { onCLS, onINP, onLCP } from 'web-vitals'
import App from './App'
import './styles/global.css'
import { initTheme } from './hooks/useTheme'

// Initialize theme before React renders to prevent flash
initTheme()

// Web Vitals monitoring — dev: console.log, prod: could be sent to Rust logger
onCLS((metric) => {
  if (import.meta.env.DEV) console.log('[vitals] CLS:', metric.value)
})
onINP((metric) => {
  if (import.meta.env.DEV) console.log('[vitals] INP:', metric.value)
})
onLCP((metric) => {
  if (import.meta.env.DEV) console.log('[vitals] LCP:', metric.value)
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
