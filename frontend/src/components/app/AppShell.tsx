/** Primary app shell — full grid layout with sidebar, library panel,
 *  header, tab bar, and content area.
 *
 *  Used when a library root is configured.
 */

import { type ReactNode } from 'react'
import Sidebar from '../Sidebar'
import LibraryPanel from '../LibraryPanel'
import Header from '../Header'
import TabBar from '../project/TabBar'
import ErrorBoundary from '../ErrorBoundary'
import OcrConfigModal from '../OcrConfigModal'
import { ToastContainer } from '../ui'
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
  const shellClass = [
    'app-shell',
    libraryPanelCollapsed ? 'app-shell--collapsed' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={shellClass}>
      <Sidebar current={currentPage} onNavigate={onNavigate} />
      {!libraryPanelCollapsed && (
        <div className="app-shell__library-panel">
          <LibraryPanel />
        </div>
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
      <ToastContainer />
      <OcrConfigModal />
    </div>
  )
}
