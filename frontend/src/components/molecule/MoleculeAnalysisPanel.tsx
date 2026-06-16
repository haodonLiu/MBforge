import { Tabs, TabPanel, EmptyState } from '../ui'
import SessionOverview from '../sar/SessionOverview'
import OverviewTab from '../sar/OverviewTab'
import RGroupTab from '../sar/RGroupTab'
import CliffsTab from '../sar/CliffsTab'
import AnalyticsTab from './analysis/AnalyticsTab'
import RelationsTab from './analysis/RelationsTab'
import type { MoleculeRecord, SARSession } from '../../types'
import type { AnalysisTab } from '../../hooks/useMoleculeAnalysis'

export interface MoleculeAnalysisPanelProps {
  analysisInput: MoleculeRecord[]
  sarSession: SARSession | null
  activeTab: AnalysisTab
  onTabChange: (tab: AnalysisTab) => void
  projectRoot: string | null
  onRefresh: () => void
}

export default function MoleculeAnalysisPanel({
  analysisInput,
  sarSession,
  activeTab,
  onTabChange,
  projectRoot,
  onRefresh,
}: MoleculeAnalysisPanelProps) {
  if (analysisInput.length === 0) {
    return <EmptyState message="请选择或导入分子以开始分析" />
  }

  const items = [
    { key: 'overview', label: 'Overview' },
    { key: 'rgroup', label: 'R-Group' },
    { key: 'cliffs', label: 'Activity Cliffs' },
    { key: 'analytics', label: 'Analytics' },
    { key: 'relations', label: 'Relations' },
  ]

  return (
    <div>
      <Tabs
        items={items}
        activeKey={activeTab}
        onChange={(key) => onTabChange(key as AnalysisTab)}
      />

      <TabPanel activeKey={activeTab} tabKey="overview">
        {sarSession && (
          <>
            <SessionOverview session={sarSession} />
            <OverviewTab session={sarSession} selectedCompoundId={null} onSelect={() => {}} />
          </>
        )}
      </TabPanel>

      <TabPanel activeKey={activeTab} tabKey="rgroup">
        {sarSession && <RGroupTab session={sarSession} onSelectCompound={() => {}} />}
      </TabPanel>

      <TabPanel activeKey={activeTab} tabKey="cliffs">
        {sarSession && projectRoot && (
          <CliffsTab session={sarSession} projectRoot={projectRoot} />
        )}
      </TabPanel>

      <TabPanel activeKey={activeTab} tabKey="analytics">
        <AnalyticsTab molecules={analysisInput} projectRoot={projectRoot} onRefresh={onRefresh} />
      </TabPanel>

      <TabPanel activeKey={activeTab} tabKey="relations">
        <RelationsTab molecules={analysisInput} />
      </TabPanel>
    </div>
  )
}
