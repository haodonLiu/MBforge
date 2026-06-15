import { useTranslation } from 'react-i18next'
import Tabs from '@/components/ui/Tabs'

interface DiscoverTabsProps {
  active: 'search' | 'chat'
  onChange: (tab: 'search' | 'chat') => void
}

export default function DiscoverTabs({ active, onChange }: DiscoverTabsProps) {
  const { t } = useTranslation()

  return (
    <Tabs
      activeKey={active}
      onChange={(key) => onChange(key as 'search' | 'chat')}
      variant="underline"
      items={[
        { key: 'search', label: t('discover.search') },
        { key: 'chat', label: t('discover.chat') },
      ]}
      style={{ marginBottom: '16px' }}
    />
  )
}
