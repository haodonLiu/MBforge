// PDF 解析栏目 — 文本切块。

import { useTranslation } from 'react-i18next'
import SettingSection, { SettingGroup } from '@/components/ui/SettingSection'
import { NumberField, ToggleField } from './SettingRow'
import type { SettingsState } from './types'

interface Props {
  settings: SettingsState
  setSettings: React.Dispatch<React.SetStateAction<SettingsState>>
}

export default function PdfParseSection({ settings, setSettings }: Props) {
  const { t } = useTranslation()
  return (
    <SettingSection>
      <SettingGroup title={t('settings.pdfParse')}>
        <NumberField
          label={t('settings.pdfChunkSize')}
          description={t('settings.pdfChunkSizeDesc')}
          value={settings.pdf_chunk_size}
          onChange={v => setSettings(s => ({ ...s, pdf_chunk_size: v }))}
          min={128}
          max={4096}
          step={64}
        />
        <NumberField
          label={t('settings.pdfChunkOverlap')}
          description={t('settings.pdfChunkOverlapDesc')}
          value={settings.pdf_chunk_overlap}
          onChange={v => setSettings(s => ({ ...s, pdf_chunk_overlap: v }))}
          min={0}
          max={512}
          step={16}
        />
      </SettingGroup>
      <SettingGroup title={t('settings.moldet')}>
        <ToggleField
          label={t('settings.autoMoldetOnImport')}
          description={t('settings.autoMoldetOnImportDesc')}
          value={settings.auto_moldet_on_import}
          onChange={v => setSettings(s => ({ ...s, auto_moldet_on_import: v }))}
        />
        <NumberField
          label={t('settings.moldetBatchSize')}
          description={t('settings.moldetBatchSizeDesc')}
          value={settings.detection_batch_size}
          onChange={v => setSettings(s => ({ ...s, detection_batch_size: v }))}
          min={0}
          max={100}
          step={1}
        />
      </SettingGroup>
      <SettingGroup title={t('settings.ingest')}>
        <ToggleField
          label={t('settings.autoEnqueueOnImport')}
          description={t('settings.autoEnqueueOnImportDesc')}
          value={settings.auto_enqueue_on_import}
          onChange={v => setSettings(s => ({ ...s, auto_enqueue_on_import: v }))}
        />
      </SettingGroup>
      <SettingGroup title={t('settings.popo')}>
        <ToggleField
          label={t('settings.popoEnabled')}
          description={t('settings.popoEnabledDesc')}
          value={settings.popo_enabled}
          onChange={v => setSettings(s => ({ ...s, popo_enabled: v }))}
        />
      </SettingGroup>
    </SettingSection>
  )
}
