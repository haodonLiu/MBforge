/** Primary app shell — full grid layout with sidebar, library panel,
 *  header, tab bar, and content area.
 *
 *  Used when a library root is configured.
 */

import { useState, type ReactNode } from 'react'
import Sidebar from '../Sidebar'
import LibraryPanel from '../LibraryPanel'
import Header from '../Header'
import TabBar from '../project/TabBar'
import ErrorBoundary from '../ErrorBoundary'
import OcrConfigModal from '../OcrConfigModal'
import { ToastContainer } from '../ui'
import { useIsMobile } from '@/styles/responsive'
import '../../styles/AppShell.css'

interface AppShellProps {
  currentPage: string
  onNavigate: (page: string) => void
  libraryPanelCollapsed: boolean
  /** The active content to render (routes or tab viewers). */
  children: ReactNode
}

export function AppShell({
  currentPage,
  onNavigate,
  libraryPanelCollapsed,
  children,
}: AppShellProps) {
  const isMobile = useIsMobile()
  const [isMobileLibraryOpen, setIsMobileLibraryOpen] = useState(false)
  const shellClass = [
    'app-shell',
    libraryPanelCollapsed ? 'app-shell--collapsed' : '',
    isMobileLibraryOpen ? 'app-shell--mobile-library-open' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={shellClass}>
      <Sidebar
        current={currentPage}
        onNavigate={onNavigate}
        onMobileLibraryToggle={isMobile ? () => setIsMobileLibraryOpen((open) => !open) : undefined}
      />
      {(isMobile || !libraryPanelCollapsed) && (
        <div className="app-shell__library-panel">
          <LibraryPanel />
        </div>
      )}
      {isMobileLibraryOpen && (
        <button
          type="button"
          className="app-shell__mobile-overlay"
          aria-label="Close library panel"
          onClick={() => setIsMobileLibraryOpen(false)}
        />
      )}
      <div className="app-shell__header">
        <Header gridColumn="3" currentPage={currentPage} />
      </div>
      <div className="app-shell__tab-bar">
        <TabBar />
      </div>
      <main className="app-shell__content">
        <ErrorBoundary>{children}</ErrorBoundary>
      </main>
      <ToastContainer position="bottom-right" />
      <OcrConfigModal />
    </div>
  )
}
