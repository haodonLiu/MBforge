import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { PageTitle, Tabs, TabPanel } from '@/components/ui'
import WorkspaceOverview from './WorkspaceOverview'
import WorkspaceDocumentBrowser from './WorkspaceDocumentBrowser'

interface Props {
  onSettingsOpen: () => void
}

/**
 * Workspace 页面。
 *
 * 提供「概览」与「文档」两个标签页，作为项目工作流的主入口。
 */
export default function Workspace({ onSettingsOpen }: Props) {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState('overview')

  const tabItems = [
    { key: 'overview', label: t('workspace.overview') },
    { key: 'documents', label: t('workspace.documents') },
  ]

  return (
    <div className="workspace-page">
      <PageTitle>{t('workspace.title')}</PageTitle>
      <Tabs
        items={tabItems}
        activeKey={activeTab}
        onChange={setActiveTab}
        variant="underline"
        style={{ marginTop: 16 }}
      />
      <TabPanel activeKey={activeTab} tabKey="overview">
        <WorkspaceOverview />
      </TabPanel>
      <TabPanel activeKey={activeTab} tabKey="documents">
        <WorkspaceDocumentBrowser onSettingsOpen={onSettingsOpen} />
      </TabPanel>
    </div>
  )
}
