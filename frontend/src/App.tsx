import { Suspense, useState, lazy, useEffect, useRef, useMemo } from 'react'
import { Routes, Route, useLocation, Navigate } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import { useTranslation, I18nextProvider } from 'react-i18next'
import i18n from './i18n'
import AnimatedPage from './components/animations/AnimatedPage'
import { ToastContainer, ToastProvider } from './components/ui'
import ErrorBoundary from './components/ErrorBoundary'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
// Welcome is above-the-fold and stays static for fast first paint.
import Welcome from './components/Welcome'
import LibraryPanel from './components/LibraryPanel'
import TabBar from './components/project/TabBar'
import PdfViewer from './components/project/PdfViewer'
import MarkdownViewer from './components/MarkdownViewer'
import { AppProvider, useAppContext } from './context/AppContext'
import { showToast } from './hooks/useToast'
import { useIsMobile, useIsTablet } from './styles/responsive'
import { registerGlobalErrorHandlers } from './api/http/_utils'
import { useSidecarEvents } from './hooks/useSidecarEvents'
import { useIngestNotifications } from './hooks/useIngestNotifications'
import OcrConfigModal from './components/OcrConfigModal'
import { getLibraryStatus } from './api/http/library'

// Route-level code splitting — each page becomes its own chunk.
// Heavy bundles (Chat, MoleculeLibrary) only load when the user navigates
// to them, slashing initial TTI.
import Workspace from './components/workspace/Workspace'
const Discover = lazy(() => import('./components/discover/Discover'))
const MoleculeLibrary = lazy(() => import('./components/MoleculeLibrary'))

const Notes = lazy(() => import('./components/Notes'))
const ProcessingQueue = lazy(() => import('./components/project/ProcessingQueue'))
const SettingsPage = lazy(() => import('./components/settings/SettingsPage'))

/** Lightweight fallback shown while a route chunk is being fetched. */
function RouteFallback() {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100%',
      color: 'var(--text-muted)',
      fontSize: '14px',
    }}>
      Loading...
    </div>
  )
}

export default function App() {
  return (
    <I18nextProvider i18n={i18n}>
      <AppProvider>
        <ToastProvider>
          <AppInner />
        </ToastProvider>
      </AppProvider>
    </I18nextProvider>
  )
}

function AppInner() {
  const { libraryRoot, setLibraryRoot, libraryPanelCollapsed, setLibraryPanelCollapsed, setActiveFile, openTabs, activeTabId, closeTab } = useAppContext()
  const [currentPage, setCurrentPage] = useState('workspace')
  const isMobile = useIsMobile()
  const isTablet = useIsTablet()
  const { t } = useTranslation()

  // 当前激活的标签
  const activeTab = useMemo(
    () => (activeTabId ? openTabs.find(t => t.id === activeTabId) ?? null : null),
    [activeTabId, openTabs],
  )

  useSidecarEvents()
  useIngestNotifications(libraryRoot)

  useEffect(() => {
    const cleanup = registerGlobalErrorHandlers()
    return cleanup
  }, [])

  // Listen for cross-component navigation requests (e.g. OcrApiMissingModal).
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail
      if (detail === 'settings') setCurrentPage('settings')
    }
    window.addEventListener('mbforge:navigate', handler)
    return () => window.removeEventListener('mbforge:navigate', handler)
  }, [])

  // Restore library config from backend on mount
  useEffect(() => {
    void (async () => {
      try {
        const status = await getLibraryStatus()
        if (status.configured && status.root) {
          setLibraryRoot(status.root)
        }
      } catch {
        // Backend not reachable yet — keep current state
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Keep localStorage in sync with libraryRoot so the setting persists
  const hasMountedRef = useRef(false)
  useEffect(() => {
    if (!hasMountedRef.current) {
      hasMountedRef.current = true
      return
    }
    if (libraryRoot) {
      localStorage.setItem('mbforge_library_root', libraryRoot)
    } else {
      localStorage.removeItem('mbforge_library_root')
    }
  }, [libraryRoot])

  // No library configured - show Welcome (library config)
  if (!libraryRoot) {
    return (
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr',
        gridTemplateRows: '1fr',
        height: '100vh',
      }}>
        <main style={{
          gridColumn: '1',
          gridRow: '1',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}>
          <Welcome />
        </main>
        <ToastContainer />
      </div>
    )
  }

  // Library configured - show full app with library panel
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: libraryPanelCollapsed ? '56px 0px 1fr' : '56px 220px 1fr',
      gridTemplateRows: 'auto auto 1fr auto',
      height: '100vh',
    }}>
      <Sidebar
        current={currentPage}
        onNavigate={setCurrentPage}
      />
      {!libraryPanelCollapsed && (
        <div style={{
          gridColumn: '2',
          gridRow: '1 / 5',
          background: 'var(--bg-surface)',
          borderRight: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}>
          <LibraryPanel />
        </div>
      )}
      <Header gridColumn="3" currentPage={currentPage} />
      <div style={{ gridColumn: '3' }}>
        <TabBar />
      </div>
      <main style={{
        gridColumn: '3',
        gridRow: '3 / 5',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        paddingBottom: isMobile ? 'env(safe-area-inset-bottom)' : 0,
      }}>
        <ErrorBoundary>
          <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
            {activeTabId === null ? (
              <AppRoutes />
            ) : activeTab && activeTab.type === 'pdf' ? (
              <PdfViewer
                doc={activeTab.doc}
                libraryRoot={activeTab.libraryRoot}
                onClose={() => closeTab(activeTab.id)}
              />
            ) : activeTab && activeTab.type === 'markdown' ? (
              <MarkdownViewer
                libraryRoot={activeTab.libraryRoot}
                filePath={activeTab.doc.path}
                onClose={() => closeTab(activeTab.id)}
              />
            ) : null}
          </div>
        </ErrorBoundary>
      </main>
      <ToastContainer />
      <OcrConfigModal />
    </div>
  )
}

function AppRoutes() {
  const location = useLocation()
  return (
    <AnimatePresence>
      <Routes location={location} key={location.pathname}>
        <Route path="/" element={<Navigate to="/workspace" replace />} />
        <Route
          path="/workspace"
          element={
            <Suspense fallback={<RouteFallback />}>
              <AnimatedPage><Workspace /></AnimatedPage>
            </Suspense>
          }
        />
        <Route
          path="/discover"
          element={
            <Suspense fallback={<RouteFallback />}>
              <AnimatedPage><Discover /></AnimatedPage>
            </Suspense>
          }
        />
        <Route
          path="/molecules"
          element={
            <Suspense fallback={<RouteFallback />}>
              <AnimatedPage><MoleculeLibrary /></AnimatedPage>
            </Suspense>
          }
        />
        <Route path="/analysis" element={<Navigate to="/molecules" replace />} />
        <Route
          path="/settings"
          element={
            <Suspense fallback={<RouteFallback />}>
              <AnimatedPage><SettingsPage /></AnimatedPage>
            </Suspense>
          }
        />
        <Route
          path="/queue"
          element={
            <Suspense fallback={<RouteFallback />}>
              <AnimatedPage><ProcessingQueue /></AnimatedPage>
            </Suspense>
          }
        />
        <Route
          path="/notes"
          element={
            <Suspense fallback={<RouteFallback />}>
              <AnimatedPage><Notes /></AnimatedPage>
            </Suspense>
          }
        />
      </Routes>
    </AnimatePresence>
  )
}
