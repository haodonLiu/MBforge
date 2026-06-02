import { Suspense, useState, lazy } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
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
      Loading…
    </div>
  )
}

export default function App() {
  return (
    <AppProvider>
      <AppInner />
    </AppProvider>
  )
}

function AppInner() {
  const { projectRoot, setProjectRoot } = useAppContext()
  const [currentPage, setCurrentPage] = useState('project')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [fileTreeOpen, setFileTreeOpen] = useState(true)
  const isMobile = useIsMobile()
  const isTablet = useIsTablet()

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
            Files
          </div>
          <FileTree onFileClick={(path) => {
            if (!isTauriAvailable()) {
              showToast('文件操作仅支持桌面应用环境', 'info')
              return
            }
            if (path.toLowerCase().endsWith('.pdf')) {
              invoke('open_file', { projectRoot, path }).catch((e) => {
                showToast(`无法打开: ${e}`, 'error')
              })
            } else {
              showToast(`文件: ${path}`, 'info')
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
