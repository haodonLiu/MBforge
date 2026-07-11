import { StrictMode, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { onCLS, onINP, onLCP } from 'web-vitals'
import { queryClient } from './api/query/client'
import App from './App'
import './styles/base.css'
import './styles/theme.css'
import './styles/global.css'
import './styles/processing-queue.css'
import './styles/pdf-pipeline-flow.css'
import './styles/layout.css'
import './styles/workspace.css'
import './styles/discover.css'
import './styles/analysis.css'
import './styles/settings.css'
import './styles/pdf-viewer.css'
import './styles/notes.css'
import './styles/library.css'
import './styles/molecule-display.css'
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

function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  )
}

createRoot(document.getElementById('root') ?? document.body).render(
  <StrictMode>
    <BrowserRouter>
      <Providers>
        <App />
      </Providers>
    </BrowserRouter>
  </StrictMode>,
)
