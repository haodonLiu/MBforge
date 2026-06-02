import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { listMoleculesTauri, searchMoleculesTauri } from '../api/tauri/molecule'
import type { MoleculeRecord } from '../types'
import { FlaskIcon, SearchIcon } from './icons'
import { useAppContext } from '../context/AppContext'
import { StaggerContainer, StaggerItem } from './animations/StaggerContainer'
import PageContainer from '../components/ui/PageContainer'
import PageTitle from '../components/ui/PageTitle'
import CardGrid from '../components/ui/CardGrid'
import Card from '../components/ui/Card'
import IconContainer from '../components/ui/IconContainer'
import Caption from '../components/ui/Caption'
import BodyText from '../components/ui/BodyText'
import Skeleton from '../components/ui/Skeleton'
import Button from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import { AddMoleculeDialog } from '../components/ui/AddMoleculeDialog'

export default function MoleculeLibrary() {
  const { projectRoot } = useAppContext()
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const [molecules, setMolecules] = useState<MoleculeRecord[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showAddDialog, setShowAddDialog] = useState(false)

  const loadMolecules = async () => {
    if (!projectRoot) {
      setMolecules([])
      return
    }
    setIsLoading(true)
    setError(null)
    try {
      let resp
      if (search.trim()) {
        resp = await searchMoleculesTauri(projectRoot, search.trim())
      } else {
        resp = await listMoleculesTauri(projectRoot, 100, 0)
      }
      if (resp.success && resp.molecules) {
        setMolecules(resp.molecules)
      } else {
        setMolecules([])
      }
    } catch (e) {
      setMolecules([])
      setError(e instanceof Error ? e.message : t('mol.loadFailed'))
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

  return (
    <PageContainer>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '24px',
      }}>
        <PageTitle>{t('mol.title')}</PageTitle>
        <Button variant="primary" size="sm" onClick={() => setShowAddDialog(true)}>{t('mol.add')}</Button>
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
          placeholder={projectRoot ? t('mol.search') : t('mol.searchNoProject')}
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
        <Button variant="primary" size="sm" onClick={handleSearch} disabled={!projectRoot}>
          {t('mol.searchBtn')}
        </Button>
      </div>

      {isLoading ? (
        <StaggerContainer stagger={0.05}>
          <CardGrid>
            {Array.from({ length: 6 }).map((_, i) => (
              <StaggerItem key={i}>
                <Skeleton variant="card" count={1} />
              </StaggerItem>
            ))}
          </CardGrid>
        </StaggerContainer>
      ) : error ? (
        <EmptyState message={error} error />
      ) : (
        <StaggerContainer>
          <CardGrid>
            {molecules.map(mol => (
              <StaggerItem key={mol.mol_id}>
                <Card hoverable>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    marginBottom: '12px',
                  }}>
                    <IconContainer size={40}>
                      <FlaskIcon size={20} />
                    </IconContainer>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '15px' }}>{mol.name || mol.mol_id}</div>
                      <Caption>{mol.source_doc || t('mol.unknownSource')}</Caption>
                    </div>
                  </div>
                  <BodyText size="sm" style={{
                    fontFamily: 'SF Mono, monospace',
                    wordBreak: 'break-all',
                    background: 'var(--bg-base)',
                    padding: '8px',
                    borderRadius: '6px',
                  }}>
                    {mol.esmiles}
                  </BodyText>
                  {mol.activity !== null && mol.activity !== undefined && (
                    <BodyText size="sm" style={{ marginTop: '12px' }}>
                       {t('mol.activity')}: {mol.activity.toFixed(2)} {mol.units || 'nM'}
                    </BodyText>
                  )}
                </Card>
              </StaggerItem>
            ))}
          </CardGrid>
        </StaggerContainer>
      )}

      {projectRoot && (
        <AddMoleculeDialog
          open={showAddDialog}
          onClose={() => setShowAddDialog(false)}
          projectRoot={projectRoot}
          onAdded={loadMolecules}
        />
      )}
    </PageContainer>
  )
}
