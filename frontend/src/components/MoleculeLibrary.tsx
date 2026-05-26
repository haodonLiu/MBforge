import { useState, useEffect } from 'react'
import { listMolecules, searchMolecules } from '../api/client'
import type { MoleculeRecord } from '../types'
import { FlaskIcon, SearchIcon } from './icons'

function getProjectRoot(): string {
  return localStorage.getItem('mbforge_project_root') || ''
}

export default function MoleculeLibrary() {
  const [search, setSearch] = useState('')
  const [molecules, setMolecules] = useState<MoleculeRecord[]>([])
  const [isLoading, setIsLoading] = useState(false)

  const loadMolecules = async () => {
    const projectRoot = getProjectRoot()
    if (!projectRoot) {
      setMolecules([])
      return
    }
    setIsLoading(true)
    try {
      if (search.trim()) {
        const resp = await searchMolecules(projectRoot, search.trim())
        if (resp.success && resp.molecules) {
          setMolecules(resp.molecules)
        } else {
          setMolecules([])
        }
      } else {
        const resp = await listMolecules(projectRoot, 100, 0)
        if (resp.success && resp.molecules) {
          setMolecules(resp.molecules)
        } else {
          setMolecules([])
        }
      }
    } catch (e) {
      setMolecules([])
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadMolecules()
  }, [])

  const handleSearch = () => {
    loadMolecules()
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  const projectRoot = getProjectRoot()

  return (
    <div style={{
      flex: 1,
      padding: '32px',
      overflow: 'auto',
      display: 'flex',
      flexDirection: 'column',
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '24px',
      }}>
        <h1 style={{
          fontSize: 'var(--font-size-title)',
          fontWeight: 600,
        }}>分子库</h1>
        <button className="btn btn-primary" onClick={() => alert('添加分子功能即将推出')}>+ 添加分子</button>
      </div>

      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        padding: '12px 16px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: '10px',
        marginBottom: '20px',
      }}>
        <SearchIcon size={18} />
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={projectRoot ? '搜索分子...' : '请先打开或创建一个项目'}
          disabled={!projectRoot}
          style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            outline: 'none',
            fontSize: '14px',
            color: 'var(--text-primary)',
            fontFamily: 'inherit',
          }}
        />
        <button
          onClick={handleSearch}
          disabled={!projectRoot}
          className="btn btn-primary"
          style={{ padding: '6px 16px', fontSize: '13px' }}
        >
          搜索
        </button>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>加载中...</div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: '16px',
        }}>
          {molecules.map(mol => (
            <div key={mol.mol_id} style={{
              padding: '20px',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: '12px',
              transition: 'all 0.2s',
              cursor: 'pointer',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = 'var(--accent)'
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.06)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = 'var(--border)'
              e.currentTarget.style.boxShadow = 'none'
            }}
            >
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                marginBottom: '12px',
              }}>
                <div style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '10px',
                  background: 'var(--accent-muted)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--accent)',
                }}>
                  <FlaskIcon size={20} />
                </div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '15px' }}>{mol.name || mol.mol_id}</div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{mol.source_doc || '未知来源'}</div>
                </div>
              </div>
              <div style={{
                fontSize: '12px',
                color: 'var(--text-secondary)',
                fontFamily: 'SF Mono, monospace',
                wordBreak: 'break-all',
                background: 'var(--bg-base)',
                padding: '8px',
                borderRadius: '6px',
              }}>
                {mol.smiles}
              </div>
              {mol.activity !== null && mol.activity !== undefined && (
                <div style={{
                  marginTop: '12px',
                  fontSize: '13px',
                  color: 'var(--text-secondary)',
                }}>
                  活性: {mol.activity.toFixed(2)} {mol.units || 'nM'}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
