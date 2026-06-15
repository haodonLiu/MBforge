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
      <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
        {activeTab === 'search' ? (
          <SearchTab initialQuery={sharedQuery} onQueryChange={setSharedQuery} />
        ) : (
          <ChatTab initialQuery={sharedQuery} />
        )}
      </div>
    </PageContainer>
  )
}
