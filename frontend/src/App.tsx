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
import ProjectScope from './components/ProjectScope'
import TabBar from './components/project/TabBar'
import PdfViewer from './components/project/PdfViewer'
import MarkdownViewer from './components/MarkdownViewer'
import { AppProvider, useAppContext } from './context/AppContext'
import { showToast } from './hooks/useToast'
import { useIsMobile, useIsTablet } from './styles/responsive'
import { registerGlobalErrorHandlers } from './api/tauri/_utils'
import { useSidecarEvents } from './hooks/useSidecarEvents'
import { useIngestNotifications } from './hooks/useIngestNotifications'
import OcrConfigModal from './components/OcrConfigModal'
import { openProject } from './api/tauri/project'

function getContentColumn(showProjectScope: boolean): '2' | '3' {
  return showProjectScope ? '3' : '2'
}

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
  const { t } = useTranslation()
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        color: 'var(--text-muted)',
        fontSize: '14px',
      }}
    >
      {t('common.loading')}
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
  const { projectRoot, setProjectRoot, setActiveFile, openTabs, activeTabId, closeTab } = useAppContext()
  const [currentPage, setCurrentPage] = useState('workspace')
  const [projectScopeOpen, setProjectScopeOpen] = useState(true)
  const isMobile = useIsMobile()
  const isTablet = useIsTablet()
  const { t } = useTranslation()

  // 当前激活的标签
  const activeTab = useMemo(
    () => (activeTabId ? openTabs.find(t => t.id === activeTabId) ?? null : null),
    [activeTabId, openTabs],
  )

  useSidecarEvents()
  useIngestNotifications(projectRoot)

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

  // Restore the last-opened project on app start, so the user does not have
  // to re-pick the folder every time. The path is re-validated by calling
  // ``open_project``; if the folder was deleted or is no longer a valid
  // project, the localStorage entry is cleared and Welcome re-appears.
  useEffect(() => {
    void (async () => {
      const saved = localStorage.getItem('mbforge_project_root')
      if (!saved) return
      try {
        const resp = await openProject(saved)
        if (resp.success) {
          setProjectRoot(resp.project.root)
          setCurrentPage('workspace')
        } else {
          localStorage.removeItem('mbforge_project_root')
        }
      } catch {
        localStorage.removeItem('mbforge_project_root')
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Keep localStorage in sync with projectRoot so the "switch project" flow
  // (Sidebar.onSwitchProject -> setProjectRoot('')) actually clears the
  // saved path — otherwise the next app restart would auto-restore the
  // old project, contradicting the user's intent. The useRef skip-on-first-run
  // avoids racing with the restore useEffect above (both fire on mount;
  // without the skip, the sync would clear localStorage before the restore
  // could read it).
  const hasMountedRef = useRef(false)
  useEffect(() => {
    if (!hasMountedRef.current) {
      hasMountedRef.current = true
      return
    }
    if (projectRoot) {
      localStorage.setItem('mbforge_project_root', projectRoot)
    } else {
      localStorage.removeItem('mbforge_project_root')
    }
  }, [projectRoot])

  const handleProjectOpened = (root: string) => {
    setProjectRoot(root)
    setCurrentPage('workspace')
  }

  // No project open - show Welcome only
  if (!projectRoot) {
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
          <Welcome onProjectOpened={handleProjectOpened} />
        </main>
        <ToastContainer />
      </div>
    )
  }

  // 移动端：文件树默认关闭，Sidebar 简化
  const effectiveProjectScopeOpen = projectScopeOpen && !isMobile
  const showProjectScope = effectiveProjectScopeOpen && !isTablet
  const contentColumn = getContentColumn(showProjectScope)

  // Project open - show full app with file tree
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: (() => {
        if (showProjectScope) return '56px 220px 1fr'
        return '56px 1fr'
      })(),
      gridTemplateRows: 'auto auto 1fr auto',
      height: '100vh',
    }}>
      <Sidebar
        current={currentPage}
        onNavigate={setCurrentPage}
        onSwitchProject={async () => {
          const ok = window.confirm(t('nav.confirmSwitchProject'))
          if (ok) setProjectRoot('')
        }}
        projectScopeOpen={projectScopeOpen}
        onToggleProjectScope={() => setProjectScopeOpen(!projectScopeOpen)}
      />
      {showProjectScope && (
        <div style={{
          gridColumn: '2',
          gridRow: '1 / 5',
          background: 'var(--bg-surface)',
          borderRight: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}>
          <div style={{
            padding: '12px 14px',
            borderBottom: '1px solid var(--border)',
            fontSize: '12px',
            fontWeight: 600,
            color: 'var(--text-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
          }}>
            {t('nav.projectScope')}
          </div>
          <ProjectScope onFileClick={(path) => {
            // 走 setActiveFile → ProjectView.useEffect → 应用内 PdfViewer/MarkdownViewer
            const lower = path.toLowerCase()
            if (lower.endsWith('.pdf')) {
              setActiveFile({ path, type: 'pdf', mode: 'read' })
            } else if (lower.endsWith('.md') || lower.endsWith('.markdown')) {
              setActiveFile({ path, type: 'markdown' })
            } else {
              showToast(`${t('common.project')}: ${path}`, 'info')
            }
          }} />
        </div>
      )}
      <Header gridColumn={contentColumn} />
      <div style={{ gridColumn: contentColumn }}>
        <TabBar />
      </div>
      <main style={{
        gridColumn: contentColumn,
        gridRow: '3 / 5',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        paddingBottom: isMobile ? 'env(safe-area-inset-bottom)' : 0,
      }}>
        <ErrorBoundary>
          <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
            {activeTabId === null ? (
              <AppRoutes projectRoot={projectRoot} />
            ) : activeTab && activeTab.type === 'pdf' ? (
              <PdfViewer
                doc={activeTab.doc}
                projectRoot={activeTab.projectRoot}
                onClose={() => closeTab(activeTab.id)}
              />
            ) : activeTab && activeTab.type === 'markdown' ? (
              <MarkdownViewer
                projectRoot={activeTab.projectRoot}
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

function AppRoutes({ projectRoot }: { projectRoot: string }) {
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
              <AnimatedPage><ProcessingQueue projectRoot={projectRoot} /></AnimatedPage>
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
