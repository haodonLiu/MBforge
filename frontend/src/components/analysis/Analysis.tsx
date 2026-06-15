import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { PageContainer, PageTitle } from '@/components/ui'
import SarPanel from './SarPanel'

type AnalysisPanel = 'sar' | 'cluster' | 'similarity'

interface NavItem {
  key: AnalysisPanel
  labelKey: string
}

const NAV_ITEMS: NavItem[] = [
  { key: 'sar', labelKey: 'analysis.sar' },
  { key: 'cluster', labelKey: 'analysis.cluster' },
  { key: 'similarity', labelKey: 'analysis.similarity' },
]

function PlaceholderPanel({ title }: { title: string }) {
  return (
    <div className="analysis-placeholder">
      <PageTitle>{title}</PageTitle>
    </div>
  )
}

export default function Analysis() {
  const { t } = useTranslation()
  const [activePanel, setActivePanel] = useState<AnalysisPanel>('sar')

  return (
    <PageContainer className="analysis-page" noPadding>
      <aside className="analysis-sidebar">
        <div className="analysis-sidebar-header">
          {t('nav.analysis')}
        </div>
        <nav style={{ padding: '8px' }}>
          {NAV_ITEMS.map(item => {
            const isActive = activePanel === item.key
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => setActivePanel(item.key)}
                className={isActive ? 'analysis-nav-button analysis-nav-button-active' : 'analysis-nav-button'}
                aria-current={isActive ? 'page' : undefined}
              >
                {t(item.labelKey)}
              </button>
            )
          })}
        </nav>
      </aside>

      <main className="analysis-content">
        {activePanel === 'sar' && <SarPanel />}
        {activePanel === 'cluster' && <PlaceholderPanel title={t('analysis.cluster')} />}
        {activePanel === 'similarity' && <PlaceholderPanel title={t('analysis.similarity')} />}
      </main>
    </PageContainer>
  )
}
