import AIModelsSection from '@/components/settings/sections/AIModelsSection'
import type { SettingsState } from '@/components/settings/types'

interface Props {
  settings: SettingsState
  setSettings: React.Dispatch<React.SetStateAction<SettingsState>>
}

export default function LlmTab({ settings, setSettings }: Props) {
  return <AIModelsSection settings={settings} setSettings={setSettings} />
}
