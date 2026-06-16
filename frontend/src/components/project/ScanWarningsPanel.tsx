import { useTranslation } from 'react-i18next'
import Card from '../ui/Card'
import Button from '../ui/Button'
import BodyText from '../ui/BodyText'
import Caption from '../ui/Caption'
import { AlertIcon } from '../icons'
import type { ScanWarning } from '../../api/tauri'
import { PAPERS_DIR, NOTES_DIR } from '../../config/folderLayout'

interface ScanWarningsPanelProps {
  warnings: ScanWarning[]
  onDismiss: () => void
}

export default function ScanWarningsPanel({ warnings, onDismiss }: ScanWarningsPanelProps) {
  const { t } = useTranslation()
  if (warnings.length === 0) return null
  return (
    <Card padding="14px 18px" className="project-warnings-card">
      <div className="project-warnings-inner">
        <div className="project-warnings-icon">
          <AlertIcon size={18} />
        </div>
        <div className="project-warnings-content">
          <BodyText size="sm" className="project-warnings-title">
            {t('scan.skippedFiles', { count: warnings.length })}
          </BodyText>
          <div className="project-warnings-list">
            {warnings.slice(0, 50).map((w, i) => (
              <Caption key={i} className="project-warnings-item">
                <strong className="project-warnings-path">{w.path}</strong>
                <span className="project-warnings-reason"> — {w.reason}</span>
              </Caption>
            ))}
            {warnings.length > 50 && (
              <Caption className="project-warnings-more">
                {t('scan.andMore', { count: warnings.length - 50 })}
              </Caption>
            )}
          </div>
          <Caption className="project-warnings-hint">
            {t('scan.moveHint', { papers: PAPERS_DIR, notes: NOTES_DIR })}
          </Caption>
        </div>
        <Button variant="ghost" size="sm" onClick={onDismiss}>
          {t('scan.dismiss')}
        </Button>
      </div>
    </Card>
  )
}
