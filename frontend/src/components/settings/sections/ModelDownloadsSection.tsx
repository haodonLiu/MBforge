// 模型下载栏目 — 缓存目录输入与模型列表合并展示，无小标题。

import SettingSection from '../../ui/SettingSection'
import ModelsTab from '../ModelsTab'
import type { SettingsState } from '../types'

interface Props {
  settings: SettingsState
  setSettings: React.Dispatch<React.SetStateAction<SettingsState>>
}

export default function ModelDownloadsSection({ settings, setSettings }: Props) {
  return (
    <SettingSection>
      <ModelsTab
        modelCacheDir={settings.model_cache_dir}
        onCacheDirChange={v => setSettings(s => ({ ...s, model_cache_dir: v }))}
      />
    </SettingSection>
  )
}
