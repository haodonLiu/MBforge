import { Suspense, useState, lazy, useEffect } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import { useTranslation, I18nextProvider } from 'react-i18next'
import i18n from './i18n'
import AnimatedPage from './components/animations/AnimatedPage'
import { ToastContainer } from './components/ui'
import ErrorBoundary from './components/ErrorBoundary'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
// Welcome is above-the-fold and stays static for fast first paint.
import Welcome from './components/Welcome'
import SettingsModal from './components/SettingsModal'
import FileTree from './components/FileTree'
import { AppProvider, useAppContext } from './context/AppContext'
import { invoke } from '@tauri-apps/api/core'
import { isTauriAvailable } from './api/tauri-bridge'
import { showToast } from './hooks/useToast'
import { useIsMobile, useIsTablet } from './styles/responsive'
import { registerGlobalErrorHandlers } from './api/tauri/_utils'
import { useSidecarEvents } from './hooks/useSidecarEvents'

// Route-level code splitting — each page becomes its own chunk.
// Heavy bundles (Chat, MoleculeLibrary, ProjectView, SARAnalysis) only
// load when the user navigates to them, slashing initial TTI.
const ProjectView = lazy(() => import('./components/ProjectView'))
const Search = lazy(() => import('./components/Search'))
const Chat = lazy(() => import('./components/Chat'))
const MoleculeLibrary = lazy(() => import('./components/MoleculeLibrary'))
const Workflow = lazy(() => import('./components/Workflow'))
const SARAnalysis = lazy(() => import('./components/SARAnalysis'))
const Dashboard = lazy(() => import('./components/Dashboard'))
const Notes = lazy(() => import('./components/Notes'))

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
        <AppInner />
      </AppProvider>
    </I18nextProvider>
  )
}

function AppInner() {
  const { projectRoot, setProjectRoot } = useAppContext()
  const [currentPage, setCurrentPage] = useState('project')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [fileTreeOpen, setFileTreeOpen] = useState(true)
  const isMobile = useIsMobile()
  const isTablet = useIsTablet()
  const { t } = useTranslation()

  useSidecarEvents()

  useEffect(() => {
    const cleanup = registerGlobalErrorHandlers()
    return cleanup
  }, [])

  const handleProjectOpened = (root: string) => {
    setProjectRoot(root)
    setCurrentPage('project')
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
        <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
        <ToastContainer />
      </div>
    )
  }

  // 移动端：文件树默认关闭，Sidebar 简化
  const effectiveFileTreeOpen = fileTreeOpen && !isMobile
  const showFileTree = effectiveFileTreeOpen && !isTablet

  // Project open - show full app with file tree
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: effectiveFileTreeOpen
        ? (showFileTree ? '56px 220px 1fr' : '56px 1fr')
        : '56px 1fr',
      gridTemplateRows: 'auto 1fr auto',
      height: '100vh',
    }}>
      <Sidebar
        current={currentPage}
        onNavigate={setCurrentPage}
        onSettingsOpen={() => setSettingsOpen(true)}
        onSwitchProject={() => setProjectRoot('')}
        fileTreeOpen={fileTreeOpen}
        onToggleFileTree={() => setFileTreeOpen(!fileTreeOpen)}
      />
      {showFileTree && (
        <div style={{
          gridColumn: '2',
          gridRow: '1 / 4',
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
            {t('nav.fileTree')}
          </div>
          <FileTree onFileClick={(path) => {
            if (!isTauriAvailable()) {
              showToast(t('error.description'), 'info')
              return
            }
            if (path.toLowerCase().endsWith('.pdf')) {
              invoke('open_file', { project_root: projectRoot, path }).catch((e: unknown) => {
                showToast(`${t('error.title')}: ${String(e)}`, 'error')
              })
            } else {
              showToast(`${t('common.project')}: ${path}`, 'info')
            }
          }} />
        </div>
      )}
      <Header />
      <main style={{
        gridColumn: effectiveFileTreeOpen ? (showFileTree ? '3' : '2') : '2',
        gridRow: '2 / 3',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        paddingBottom: isMobile ? 'env(safe-area-inset-bottom)' : 0,
      }}>
        <ErrorBoundary>
          <AppRoutes />
        </ErrorBoundary>
      </main>
      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <ToastContainer />
    </div>
  )
}

function AppRoutes() {
  const location = useLocation()
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route
          path="/"
          element={
            <Suspense fallback={<RouteFallback />}>
              <AnimatedPage><ProjectView /></AnimatedPage>
            </Suspense>
          }
        />
        <Route
          path="/search"
          element={
            <Suspense fallback={<RouteFallback />}>
              <AnimatedPage><Search /></AnimatedPage>
            </Suspense>
          }
        />
        <Route
          path="/chat"
          element={
            <Suspense fallback={<RouteFallback />}>
              <AnimatedPage><Chat /></AnimatedPage>
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
        <Route
          path="/workflow"
          element={
            <Suspense fallback={<RouteFallback />}>
              <AnimatedPage><Workflow /></AnimatedPage>
            </Suspense>
          }
        />
        <Route
          path="/project"
          element={
            <Suspense fallback={<RouteFallback />}>
              <AnimatedPage><ProjectView /></AnimatedPage>
            </Suspense>
          }
        />
        <Route
          path="/sar"
          element={
            <Suspense fallback={<RouteFallback />}>
              <AnimatedPage><SARAnalysis /></AnimatedPage>
            </Suspense>
          }
        />
        <Route
          path="/dashboard"
          element={
            <Suspense fallback={<RouteFallback />}>
              <AnimatedPage><Dashboard /></AnimatedPage>
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
