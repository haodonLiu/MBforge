import { Suspense, lazy, useState, useRef, useEffect } from 'react'
import { Routes, Route, useLocation, Navigate } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import { I18nextProvider } from 'react-i18next'
import i18n from './i18n'
import AnimatedPage from './components/animations/AnimatedPage'
import { ToastProvider } from './components/ui'
import { LibraryBootstrap } from './components/app/LibraryBootstrap'
import { AppShell } from './components/app/AppShell'
import { AppProvider, useAppContext } from './context/AppContext'
import PdfViewer from './components/project/PdfViewer'
import DocumentViewer from './components/project/DocumentViewer'
import MarkdownViewer from './components/MarkdownViewer'
import { registerGlobalErrorHandlers } from './api/http/_utils'
import { useSidecarEvents } from './hooks/useSidecarEvents'
import { useIngestNotifications } from './hooks/useIngestNotifications'
import { getLibraryStatus } from './api/http/library'
import type { Tab } from './context/AppContext'
import Workspace from './components/workspace/Workspace'

const Discover = lazy(() => import('./components/discover/Discover'))
const MoleculeLibrary = lazy(() => import('./components/MoleculeLibrary'))
const Notes = lazy(() => import('./components/Notes'))
const ProcessingQueue = lazy(() => import('./components/project/ProcessingQueue'))
const SettingsPage = lazy(() => import('./components/settings/SettingsPage'))

/** Lightweight fallback shown while a route chunk is being fetched. */
function RouteFallback() {
  return (
    <div className="route-fallback">
      Loading...
    </div>
  )
}

export default function App() {
  return (
    <I18nextProvider i18n={i18n}>
      <AppProvider>
        <ToastProvider>
          <AppShellOrBootstrap />
        </ToastProvider>
      </AppProvider>
    </I18nextProvider>
  )
}

/**
 * Thin orchestrator — holds lifecycle hooks and chooses between the
 * bootstrap (no library) or the full app shell (library configured).
 */
function AppShellOrBootstrap() {
  const {
    libraryRoot,
    setLibraryRoot,
    libraryPanelCollapsed,
    openTabs,
    activeTabId,
    closeTab,
  } = useAppContext()
  const [currentPage, setCurrentPage] = useState('workspace')

  useSidecarEvents()
  useIngestNotifications(libraryRoot)

  // Register global error handlers once on mount.
  useEffect(() => {
    const cleanup = registerGlobalErrorHandlers()
    return cleanup
  }, [])

  // Listen for cross-component navigation requests.
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail
      if (detail === 'settings') setCurrentPage('settings')
    }
    window.addEventListener('mbforge:navigate', handler)
    return () => window.removeEventListener('mbforge:navigate', handler)
  }, [])

  // Restore library config from backend on mount.
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

  // Keep localStorage in sync with libraryRoot.
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

  if (!libraryRoot) {
    return <LibraryBootstrap />
  }

  return (
    <AppShell
      currentPage={currentPage}
      onNavigate={setCurrentPage}
      libraryPanelCollapsed={libraryPanelCollapsed}
    >
      {activeTabId === null ? (
        <AppRoutes />
      ) : (
        <TabContent
          activeTabId={activeTabId}
          openTabs={openTabs}
          closeTab={closeTab}
        />
      )}
    </AppShell>
  )
}

/** Switch on active tab type: pdf / markdown / document viewer. */
function TabContent({
  activeTabId,
  openTabs,
  closeTab,
}: {
  activeTabId: string
  openTabs: Tab[]
  closeTab: (id: string) => void
}) {
  const activeTab = openTabs.find(t => t.id === activeTabId) ?? null
  if (!activeTab) return null

  switch (activeTab.type) {
    case 'pdf':
      return (
        <PdfViewer
          doc={activeTab.doc}
          libraryRoot={activeTab.libraryRoot}
          onClose={() => closeTab(activeTab.id)}
        />
      )
    case 'markdown':
      return (
        <MarkdownViewer
          libraryRoot={activeTab.libraryRoot}
          filePath={activeTab.doc.path}
          onClose={() => closeTab(activeTab.id)}
        />
      )
    case 'document':
      return (
        <DocumentViewer
          doc={activeTab.doc}
          libraryRoot={activeTab.libraryRoot}
          onClose={() => closeTab(activeTab.id)}
        />
      )
    default:
      return null
  }
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
