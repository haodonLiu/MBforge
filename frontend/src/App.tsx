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

export default function App() {
  const [currentPage, setCurrentPage] = useState('welcome')
  const [settingsOpen, setSettingsOpen] = useState(false)

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '56px 1fr',
      gridTemplateRows: 'auto 1fr auto',
      height: '100vh',
    }}>
      <Sidebar current={currentPage} onNavigate={setCurrentPage} onSettingsOpen={() => setSettingsOpen(true)} />
      <Header />
      <main style={{
        gridColumn: '2',
        gridRow: '2 / 3',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        <Routes>
          <Route path="/" element={<Welcome />} />
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
