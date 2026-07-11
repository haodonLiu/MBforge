import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { createQueryClient } from '@/api/query/client'
import { AppProvider } from '@/context/AppContext'
import { ToastProvider } from '@/components/ui'
import App from '@/App'

// Mock library status endpoint — default to "not configured".
vi.mock('@/api/http/library', () => ({
  getLibraryStatus: vi.fn().mockResolvedValue({ configured: false, root: '', doc_count: 0 }),
  listDocuments: vi.fn().mockResolvedValue({ documents: [] }),
  listCollections: vi.fn().mockResolvedValue({ collections: [] }),
  importDocument: vi.fn(),
  deleteDocument: vi.fn(),
}))

// Mock i18n — just render children without translation context.
vi.mock('react-i18next', () => ({
  I18nextProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
  initReactI18next: { type: '3rdParty' },
}))

function renderApp() {
  const qc = createQueryClient()
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <AppProvider>
          <ToastProvider>
            <App />
          </ToastProvider>
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders without crashing when no library is configured', async () => {
    renderApp()
    // LibraryBootstrap renders Welcome screen.
    expect(await screen.findByText('library.configureLibrary')).toBeInTheDocument()
  })

  it('renders AppShell when library is configured', async () => {
    // Simulate: library root is already in localStorage (pre-configured).
    localStorage.setItem('mbforge_library_root', '/tmp/test-lib')

    renderApp()
    // AppShell renders sidebar with navigation items.
    // The sidebar contains buttons that render i18n keys.
    expect(await screen.findByText(/workspace/i)).toBeInTheDocument()
  })
})
