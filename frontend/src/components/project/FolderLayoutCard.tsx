import Card from '../ui/Card'
import BodyText from '../ui/BodyText'
import Caption from '../ui/Caption'
import { FOLDER_SPECS } from '../../config/folderLayout'

interface FolderLayoutCardProps {
  projectRoot: string
}

export default function FolderLayoutCard({ projectRoot }: FolderLayoutCardProps) {
  return (
    <Card padding="14px 18px" className="project-folder-layout">
      <div className="project-folder-layout-header">
        <BodyText size="sm" className="project-folder-layout-title">项目目录规范</BodyText>
        <Caption className="project-folder-layout-root">
          <code>{projectRoot || '请先打开项目'}</code>
        </Caption>
      </div>
      <div className="project-folder-layout-grid">
        {FOLDER_SPECS.map((spec) => {
          const roleColor =
            spec.role === 'input'
              ? 'rgba(22,163,74,0.18)'
              : spec.role === 'output'
                ? 'rgba(59,130,246,0.18)'
                : 'rgba(148,163,184,0.18)'
          return (
            <div key={spec.name} className="project-folder-item">
              <span className="project-folder-role" style={{ background: roleColor }}>
                {spec.role === 'input' ? 'IN' : spec.role === 'output' ? 'OUT' : 'META'}
              </span>
              <div className="project-folder-info">
                <div className="project-folder-name">{spec.name}/</div>
                <Caption className="project-folder-accepts">{spec.accepts}</Caption>
                <Caption className="project-folder-desc">{spec.description}</Caption>
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}
