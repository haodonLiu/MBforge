import { useState } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import AnimatedPage from './components/animations/AnimatedPage'
import ToastContainer from './components/Toast'
import ErrorBoundary from './components/ErrorBoundary'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
import Welcome from './components/Welcome'
import Search from './components/Search'
import Chat from './components/Chat'
import MoleculeLibrary from './components/MoleculeLibrary'
import Workflow from './components/Workflow'
import ProjectView from './components/ProjectView'
import SettingsModal from './components/SettingsModal'
import FileTree from './components/FileTree'
import { useProjectRoot } from './hooks/useProjectRoot'
import { invoke } from '@tauri-apps/api/core'
import { isTauriAvailable } from './api/tauri-bridge'
import { showToast } from './hooks/useToast'

export default function App() {
  const { projectRoot, setProjectRoot } = useProjectRoot()
  const [currentPage, setCurrentPage] = useState('project')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [fileTreeOpen, setFileTreeOpen] = useState(true)

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
      </div>
    )
  }

  // Project open - show full app with file tree
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: fileTreeOpen ? '56px 220px 1fr' : '56px 1fr',
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
      {fileTreeOpen && (
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
              invoke('open_file', { path }).catch((e) => {
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
        gridColumn: fileTreeOpen ? '3' : '2',
        gridRow: '2 / 3',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
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
      </Routes>
    </AnimatePresence>
  )
}
