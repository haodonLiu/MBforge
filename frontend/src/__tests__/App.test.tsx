import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { I18nextProvider } from 'react-i18next'
import { createQueryClient } from '@/api/query/client'
import { AppProvider } from '@/context/AppContext'
import { ToastProvider } from '@/components/ui'
import i18n from '@/i18n/index'
import App from '@/App'

// Mock library status endpoint — default to "not configured".
vi.mock('@/api/http/library', () => ({
  getLibraryStatus: vi.fn().mockResolvedValue({ configured: false, root: '', doc_count: 0 }),
  listDocuments: vi.fn().mockResolvedValue({ documents: [] }),
  importDocument: vi.fn(),
  deleteDocument: vi.fn(),
}))

function renderApp() {
  const qc = createQueryClient()
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <I18nextProvider i18n={i18n}>
          <AppProvider>
            <ToastProvider>
              <App />
            </ToastProvider>
          </AppProvider>
        </I18nextProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders Welcome screen when no library is configured', async () => {
    renderApp()
    // Welcome screen shows the configure button / title.
    expect(await screen.findByText(/MBForge/i)).toBeInTheDocument()
  })

  it('renders AppShell when library is configured', async () => {
    // Override mock for this test.
    const library = await import('@/api/http/library')
    vi.mocked(library.getLibraryStatus).mockResolvedValue({
      configured: true,
      root: '/tmp/test-lib',
      doc_count: 5,
    })

    renderApp()
    // AppShell renders the sidebar navigation.
    expect(await screen.findByText(/Workspace/i)).toBeInTheDocument()
  })
})
