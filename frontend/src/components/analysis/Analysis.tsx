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

export default function Analysis() {
  const { t } = useTranslation()
  const [activePanel, setActivePanel] = useState<AnalysisPanel>('sar')

  return (
    <PageContainer className="analysis-page" noPadding>
      <aside className="analysis-sidebar">
        <div
          style={{
            padding: '16px 14px',
            borderBottom: '1px solid var(--border)',
            fontSize: '12px',
            fontWeight: 600,
            color: 'var(--text-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
          }}
        >
          {t('nav.analysis')}
        </div>
        <nav style={{ padding: '8px' }}>
          {NAV_ITEMS.map(item => (
            <button
              key={item.key}
              type="button"
              onClick={() => setActivePanel(item.key)}
              className={activePanel === item.key ? 'active' : ''}
              style={{
                display: 'block',
                width: '100%',
                padding: '10px 12px',
                marginBottom: '4px',
                textAlign: 'left',
                fontSize: '14px',
                color: activePanel === item.key ? 'var(--accent)' : 'var(--text-primary)',
                background: activePanel === item.key ? 'var(--accent-subtle)' : 'transparent',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
              }}
            >
              {t(item.labelKey)}
            </button>
          ))}
        </nav>
      </aside>

      <main className="analysis-content">
        {activePanel === 'sar' && <SarPanel />}
        {activePanel === 'cluster' && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              color: 'var(--text-muted)',
            }}
          >
            <PageTitle>{t('analysis.cluster')}</PageTitle>
          </div>
        )}
        {activePanel === 'similarity' && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              color: 'var(--text-muted)',
            }}
          >
            <PageTitle>{t('analysis.similarity')}</PageTitle>
          </div>
        )}
      </main>
    </PageContainer>
  )
}
