/**
 * General tab — UI preferences (theme, language, recent projects).
 * PDF processing was carved out into its own tab; see PdfProcessingTab.
 */

import GeneralSection from '@/components/settings/sections/GeneralSection'
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
      <RecentProjectsSection />
    </div>
  )
}