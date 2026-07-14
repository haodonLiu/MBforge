/**
 * General tab — UI preferences (theme and language).
 * PDF processing was carved out into its own tab; see PdfProcessingTab.
 */

import GeneralSection from '@/components/settings/GeneralSection'
import type { SettingsState } from '@/components/settings/types'

interface Props {
  settings: SettingsState
  setSettings: React.Dispatch<React.SetStateAction<SettingsState>>
}

export default function GeneralTab({ settings, setSettings }: Props) {
  return <GeneralSection settings={settings} setSettings={setSettings} />
}
