// 模型下载栏目 — 缓存目录配置 + 原有下载管理 tab。

import { useTranslation } from 'react-i18next'
import SettingSection, { SettingGroup } from '../../ui/SettingSection'
import { TextField, CustomField } from '../SettingRow'
import ModelsTab from '../ModelsTab'
import type { SettingsState } from '../types'

interface Props {
  settings: SettingsState
  setSettings: React.Dispatch<React.SetStateAction<SettingsState>>
}

export default function ModelDownloadsSection({ settings, setSettings }: Props) {
  const { t } = useTranslation()

  return (
    <SettingSection>
      <SettingGroup title={t('settings.modelCache')}>
        <TextField
          label={t('settings.modelCacheDir')}
          description={t('settings.modelCacheDirDesc')}
          value={settings.model_cache_dir}
          onChange={v => setSettings(s => ({ ...s, model_cache_dir: v }))}
          placeholder="(默认：~/.cache/mbforge)"
          monospace
        />
      </SettingGroup>

      <SettingGroup title={t('settings.modelCatalog')}>
        <CustomField label={t('settings.modelCatalog')}>
          <ModelsTab />
        </CustomField>
      </SettingGroup>
    </SettingSection>
  )
}
