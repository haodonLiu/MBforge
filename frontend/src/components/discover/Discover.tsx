import { useState } from 'react'
import PageContainer from '@/components/ui/PageContainer'
import DiscoverTabs from './DiscoverTabs'
import SearchTab from './SearchTab'
import ChatTab from './ChatTab'

export default function Discover() {
  const [activeTab, setActiveTab] = useState<'search' | 'chat'>('search')
  const [sharedQuery, setSharedQuery] = useState('')

  return (
    <PageContainer>
      <DiscoverTabs active={activeTab} onChange={setActiveTab} />
      <div className="discover-content">
        <div
          className={`discover-tab-panel${activeTab !== 'search' ? ' discover-tab-panel-hidden' : ''}`}
        >
          <SearchTab query={sharedQuery} onQueryChange={setSharedQuery} />
        </div>
        <div
          className={`discover-tab-panel${activeTab !== 'chat' ? ' discover-tab-panel-hidden' : ''}`}
        >
          <ChatTab query={sharedQuery} onQueryChange={setSharedQuery} />
        </div>
      </div>
    </PageContainer>
  )
}
