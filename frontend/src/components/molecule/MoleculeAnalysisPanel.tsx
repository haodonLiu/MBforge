import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Tabs, TabPanel, EmptyState } from '../ui'
import SessionOverview from '@/components/sar/SessionOverview'
import OverviewTab from '@/components/sar/OverviewTab'
import RGroupTab from '@/components/sar/RGroupTab'
import CliffsTab from '@/components/sar/CliffsTab'
import AnalyticsTab from '@/components/molecule/analysis/AnalyticsTab'
import RelationsTab from '@/components/molecule/analysis/RelationsTab'
import { moleculesToSession } from '@/components/sar/utils'
import type { MoleculeRecord, SARSession } from '@/types'
import type { AnalysisTab } from '@/hooks/useMoleculeAnalysis'

export interface MoleculeAnalysisPanelProps {
  analysisInput: MoleculeRecord[]
  sarSession: SARSession | null
  activeTab: AnalysisTab
  onTabChange: (tab: AnalysisTab) => void
  projectRoot: string | null
  onRefresh: () => void
}

const ANALYSIS_INPUT_LIMIT = 200

export default function MoleculeAnalysisPanel({
  analysisInput,
  sarSession: _sarSession,
  activeTab,
  onTabChange,
  projectRoot,
  onRefresh,
}: MoleculeAnalysisPanelProps) {
  const { t } = useTranslation()

  const effectiveInput = useMemo(
    () => analysisInput.slice(0, ANALYSIS_INPUT_LIMIT),
    [analysisInput],
  )

  const effectiveSession = useMemo(
    () => (effectiveInput.length > 0 ? moleculesToSession(effectiveInput) : null),
    [effectiveInput],
  )

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
      {analysisInput.length > ANALYSIS_INPUT_LIMIT && (
        <div
          style={{
            marginBottom: 12,
            padding: '10px 14px',
            borderRadius: 8,
            background: 'var(--info-muted)',
            color: 'var(--info)',
            fontSize: 13,
          }}
          role="status"
        >
          {t('mol.analysisLimited')}
        </div>
      )}

      <Tabs
        items={items}
        activeKey={activeTab}
        onChange={(key) => onTabChange(key as AnalysisTab)}
      />

      <TabPanel activeKey={activeTab} tabKey="overview">
        {effectiveSession && (
          <>
            <SessionOverview session={effectiveSession} />
            <OverviewTab session={effectiveSession} selectedCompoundId={null} onSelect={() => {}} />
          </>
        )}
      </TabPanel>

      <TabPanel activeKey={activeTab} tabKey="rgroup">
        {effectiveSession && <RGroupTab session={effectiveSession} onSelectCompound={() => {}} />}
      </TabPanel>

      <TabPanel activeKey={activeTab} tabKey="cliffs">
        {effectiveSession && projectRoot && (
          <CliffsTab session={effectiveSession} projectRoot={projectRoot} />
        )}
      </TabPanel>

      <TabPanel activeKey={activeTab} tabKey="analytics">
        <AnalyticsTab molecules={effectiveInput} projectRoot={projectRoot} onRefresh={onRefresh} />
      </TabPanel>

      <TabPanel activeKey={activeTab} tabKey="relations">
        <RelationsTab molecules={effectiveInput} />
      </TabPanel>
    </div>
  )
}
