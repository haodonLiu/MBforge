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
  if (warnings.length === 0) return null
  return (
    <Card padding="14px 18px" className="project-warnings-card">
      <div className="project-warnings-inner">
        <div className="project-warnings-icon">
          <AlertIcon size={18} />
        </div>
        <div className="project-warnings-content">
          <BodyText size="sm" className="project-warnings-title">
            扫描时跳过 {warnings.length} 个文件（位置或类型不合规）
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
                ……及其他 {warnings.length - 50} 个
              </Caption>
            )}
          </div>
          <Caption className="project-warnings-hint">
            请把 PDF 移到 <code>{PAPERS_DIR}/</code>，把 MD/TXT 移到 <code>{NOTES_DIR}/</code>，然后重新扫描
          </Caption>
        </div>
        <Button variant="ghost" size="sm" onClick={onDismiss}>
          知道了
        </Button>
      </div>
    </Card>
  )
}
