import GeneralSection from '@/components/settings/sections/GeneralSection'
import PdfParseSection from '@/components/settings/sections/PdfParseSection'
import RecentProjectsSection from '@/components/settings/sections/RecentProjectsSection'
import type { SettingsState } from '@/components/settings/types'

interface Props {
  settings: SettingsState
  setSettings: React.Dispatch<React.SetStateAction<SettingsState>>
}

export default function GeneralTab({ settings, setSettings }: Props) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <GeneralSection settings={settings} setSettings={setSettings} />
      <PdfParseSection settings={settings} setSettings={setSettings} />
      <RecentProjectsSection />
    </div>
  )
}
