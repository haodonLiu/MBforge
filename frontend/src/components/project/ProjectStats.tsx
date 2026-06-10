import Card from '../ui/Card'
import Caption from '../ui/Caption'
import { FileTextIcon, FlaskIcon, FolderIcon } from '../icons'
import { StaggerContainer, StaggerItem } from '../animations/StaggerContainer'
import ResponsiveStatGrid from '../ui/ResponsiveStatGrid'
import type { DocumentEntry } from '../../types'

interface ProjectStatsProps {
  docs: DocumentEntry[]
  indexResult: { indexed: number; sections: number } | null
}

export default function ProjectStats({ docs, indexResult }: ProjectStatsProps) {
  return (
    <StaggerContainer stagger={0.08}>
      <ResponsiveStatGrid className="project-stats-grid">
        <StaggerItem>
          <Card>
            <div className="project-stat">
              <div className="project-stat-icon"><FileTextIcon size={18} /></div>
              <div>
                <div className="project-stat-value">{String(docs.length)}</div>
                <Caption>文献</Caption>
              </div>
            </div>
          </Card>
        </StaggerItem>
        <StaggerItem>
          <Card>
            <div className="project-stat">
              <div className="project-stat-icon"><FlaskIcon size={18} /></div>
              <div>
                <div className="project-stat-value">{indexResult ? String(indexResult.sections) : '—'}</div>
                <Caption>Sections</Caption>
              </div>
            </div>
          </Card>
        </StaggerItem>
        <StaggerItem>
          <Card>
            <div className="project-stat">
              <div className="project-stat-icon"><FileTextIcon size={18} /></div>
              <div>
                <div className="project-stat-value">{String(docs.filter(d => d.indexed).length)}</div>
                <Caption>已索引</Caption>
              </div>
            </div>
          </Card>
        </StaggerItem>
        <StaggerItem>
          <Card>
            <div className="project-stat">
              <div className="project-stat-icon"><FolderIcon size={18} /></div>
              <div>
                <div className="project-stat-value">{String(docs.length)}</div>
                <Caption>文件</Caption>
              </div>
            </div>
          </Card>
        </StaggerItem>
      </ResponsiveStatGrid>
    </StaggerContainer>
  )
}
