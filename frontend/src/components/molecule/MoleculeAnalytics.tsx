import { useState, useEffect, useCallback } from 'react'
import { useAppContext } from '../../context/AppContext'
import { useTranslation } from 'react-i18next'
import { showToast } from '../../hooks/useToast'
import { molStoreInit, listMoleculesTauri } from '../../api/tauri/molecule'
import type { MoleculeRecord } from '../../types'
import {
  PageContainer,
  PageTitle,
  Button,
  EmptyState,
  Tabs,
  TabPanel,
} from '../ui'
import { SearchIcon, FlaskIcon, NetworkIcon, ClusterIcon, FilterIcon } from '../icons'
import SubstructureSearchPanel from './analytics/SubstructureSearchPanel'
import AnalogSearchPanel from './analytics/AnalogSearchPanel'
import ClusterPanel from './analytics/ClusterPanel'
import RelationPanel from './analytics/RelationPanel'
import DedupPanel from './analytics/DedupPanel'

type AnalyticsTab = 'substructure' | 'analogs' | 'clusters' | 'relations' | 'dedup'

export default function MoleculeAnalytics() {
  const { projectRoot } = useAppContext()
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<AnalyticsTab>('substructure')
  const [molecules, setMolecules] = useState<MoleculeRecord[]>([])
  const [loadingMols, setLoadingMols] = useState(false)

  const initAndLoad = useCallback(async () => {
    if (!projectRoot) return
    setLoadingMols(true)
    try {
      await molStoreInit(projectRoot)
      const resp = await listMoleculesTauri(projectRoot, 500, 0)
      if (resp.success) {
        setMolecules(resp.molecules)
      }
    } catch (e) {
      showToast(t('mol.loadFailed'), 'error')
    } finally {
      setLoadingMols(false)
    }
  }, [projectRoot, t])

  useEffect(() => {
    initAndLoad()
  }, [initAndLoad])

  if (!projectRoot) {
    return (
      <PageContainer>
        <EmptyState message={t('mol.noProject')} />
      </PageContainer>
    )
  }

  return (
    <PageContainer>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <PageTitle>{t('mol.analyticsTitle') ?? '分子高级分析'}</PageTitle>
        <Button variant="secondary" size="sm" onClick={initAndLoad} loading={loadingMols}>
          刷新
        </Button>
      </div>

      <Tabs
        items={[
          { key: 'substructure', label: <><SearchIcon size={14} /> 子结构搜索</> },
          { key: 'analogs', label: <><FlaskIcon size={14} /> 活性类似物</> },
          { key: 'clusters', label: <><ClusterIcon size={14} /> 聚类分析</> },
          { key: 'relations', label: <><NetworkIcon size={14} /> 关系网络</> },
          { key: 'dedup', label: <><FilterIcon size={14} /> 批量去重</> },
        ]}
        activeKey={activeTab}
        onChange={(k) => setActiveTab(k as AnalyticsTab)}
      />

      <div style={{ marginTop: 16 }}>
        <TabPanel activeKey={activeTab} tabKey="substructure">
          <SubstructureSearchPanel />
        </TabPanel>
        <TabPanel activeKey={activeTab} tabKey="analogs">
          <AnalogSearchPanel molecules={molecules} />
        </TabPanel>
        <TabPanel activeKey={activeTab} tabKey="clusters">
          <ClusterPanel molecules={molecules} />
        </TabPanel>
        <TabPanel activeKey={activeTab} tabKey="relations">
          <RelationPanel molecules={molecules} />
        </TabPanel>
        <TabPanel activeKey={activeTab} tabKey="dedup">
          <DedupPanel molecules={molecules} onComplete={initAndLoad} />
        </TabPanel>
      </div>
    </PageContainer>
  )
}
