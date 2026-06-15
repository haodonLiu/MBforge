import ProjectView from '@/components/ProjectView'

interface Props {
  onSettingsOpen: () => void
}

/**
 * Workspace 文档浏览器。
 *
 * 复用现有的 ProjectView，提供项目内 PDF / Markdown 文档的浏览与管理。
 */
export default function WorkspaceDocumentBrowser({ onSettingsOpen }: Props) {
  return <ProjectView onSettingsOpen={onSettingsOpen} />
}
