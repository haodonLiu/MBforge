import { useState } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import AnimatedPage from './components/animations/AnimatedPage'
import { ToastContainer } from './components/ui'
import ErrorBoundary from './components/ErrorBoundary'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
import Welcome from './components/Welcome'
import Search from './components/Search'
import Chat from './components/Chat'
import MoleculeLibrary from './components/MoleculeLibrary'
import Workflow from './components/Workflow'
import ProjectView from './components/ProjectView'
import SARAnalysis from './components/SARAnalysis'
import Dashboard from './components/Dashboard'
import Notes from './components/Notes'
import SettingsModal from './components/SettingsModal'
import FileTree from './components/FileTree'
import { AppProvider, useAppContext } from './context/AppContext'
import { invoke } from '@tauri-apps/api/core'
import { isTauriAvailable } from './api/tauri-bridge'
import { showToast } from './hooks/useToast'
import { useIsMobile, useIsTablet } from './styles/responsive'

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
        <Route path="/" element={<AnimatedPage><ProjectView /></AnimatedPage>} />
        <Route path="/search" element={<AnimatedPage><Search /></AnimatedPage>} />
        <Route path="/chat" element={<AnimatedPage><Chat /></AnimatedPage>} />
        <Route path="/molecules" element={<AnimatedPage><MoleculeLibrary /></AnimatedPage>} />
        <Route path="/workflow" element={<AnimatedPage><Workflow /></AnimatedPage>} />
        <Route path="/project" element={<AnimatedPage><ProjectView /></AnimatedPage>} />
        <Route path="/sar" element={<AnimatedPage><SARAnalysis /></AnimatedPage>} />
        <Route path="/dashboard" element={<AnimatedPage><Dashboard /></AnimatedPage>} />
        <Route path="/notes" element={<AnimatedPage><Notes /></AnimatedPage>} />
      </Routes>
    </AnimatePresence>
  )
}
