import { useState } from 'react'
import { Routes, Route } from 'react-router-dom'
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
            // Open PDF in system default viewer, other files show alert
            if (path.toLowerCase().endsWith('.pdf')) {
              window.open(`file://${path}`, '_blank')
            } else {
              alert(`文件: ${path}`)
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
        <Routes>
          <Route path="/" element={<ProjectView />} />
          <Route path="/search" element={<Search />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/molecules" element={<MoleculeLibrary />} />
          <Route path="/workflow" element={<Workflow />} />
          <Route path="/project" element={<ProjectView />} />
        </Routes>
      </main>
      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  )
}
