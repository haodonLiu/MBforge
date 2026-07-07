import { useState } from 'react'
import { Tabs, TabPanel } from '../../ui'
import SubstructureSearchPanel from '../analytics/SubstructureSearchPanel'
import AnalogSearchPanel from '../analytics/AnalogSearchPanel'
import ClusterPanel from '../analytics/ClusterPanel'
import RelationPanel from '../analytics/RelationPanel'
import DedupPanel from '../analytics/DedupPanel'
import type { MoleculeRecord } from '@/types'

type AnalyticsInnerTab = 'substructure' | 'analogs' | 'clusters' | 'relations' | 'dedup'

export interface AnalyticsTabProps {
  molecules: MoleculeRecord[]
  projectRoot: string | null
  onRefresh: () => void
}

export default function AnalyticsTab({ molecules, projectRoot: _projectRoot, onRefresh }: AnalyticsTabProps) {
  const [activeTab, setActiveTab] = useState<AnalyticsInnerTab>('substructure')

  const items = [
    { key: 'substructure', label: '子结构' },
    { key: 'analogs', label: '类似物' },
    { key: 'clusters', label: '聚类' },
    { key: 'relations', label: '关系' },
    { key: 'dedup', label: '去重' },
  ]

  return (
    <div>
      <Tabs items={items} activeKey={activeTab} onChange={(key) => setActiveTab(key as AnalyticsInnerTab)} />
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
        <DedupPanel molecules={molecules} onComplete={onRefresh} />
      </TabPanel>
    </div>
  )
}
