import { useState } from 'react'
import { AlertBanner } from '../ui'
import CorrectionPanel from '../molecule/CorrectionPanel'
import { showToast } from '../../hooks/useToast'
import { molStoreUpdateBatch } from '../../api/http/molecule'
import type { MoleculeRecord } from '../../types'

interface CorrectionItem {
  id: string
  ocrSmiles: string
  ocrConfidence: number
  name?: string
  sourceDoc?: string
  context?: string
  status?: 'pending' | 'confirmed' | 'rejected' | 'corrected'
  correctedSmiles?: string
  sourceRecord?: MoleculeRecord
}

interface CorrectionTabProps {
  projectRoot: string | null
  items: CorrectionItem[]
  onItemsChange: (items: CorrectionItem[]) => void
  onComplete: (saved: number, failed: number) => void
}

export default function CorrectionTab({ projectRoot, items, onItemsChange, onComplete }: CorrectionTabProps) {
  const [saving, setSaving] = useState(false)

  const handleItemChange = (id: string, finalSmiles: string, status: 'pending' | 'confirmed' | 'rejected' | 'corrected' | undefined) => {
    onItemsChange(
      items.map(item =>
        item.id === id
          ? { ...item, correctedSmiles: finalSmiles, status: (status ?? 'pending') as typeof item.status }
          : item,
      ),
    )
  }

  const handleComplete = async (results: Array<{ id: string; finalSmiles: string; status: 'confirmed' | 'rejected' | 'corrected' }>) => {
    if (!projectRoot) {
      showToast('未选择项目', 'warning')
      return
    }
    if (results.length === 0) {
      showToast('没有可保存的结果', 'info')
      return
    }

    setSaving(true)
    try {
      const records = results
        .map(r => {
          const item = items.find(i => i.id === r.id)
          if (!item?.sourceRecord) return null
          return {
            ...item.sourceRecord,
            esmiles: r.finalSmiles,
            status: r.status,
            notes: `${item.sourceRecord.notes || ''}\n[${new Date().toISOString()}] OCR 矫正: ${r.status}`.trim(),
          }
        })
        .filter((r): r is NonNullable<typeof r> => r !== null)

      if (records.length === 0) {
        showToast('没有可保存的记录（缺少源数据）', 'warning')
        return
      }

      const result = await molStoreUpdateBatch(projectRoot, records)
      onComplete(result.updated, result.failed.length)
      const correctedCount = results.filter(r => r.status === 'corrected').length
      if (result.failed.length > 0) {
        showToast(
          `保存完成：${result.updated} 项已保存，${result.failed.length} 项失败`,
          'warning',
        )
      } else {
        showToast(
          `保存完成：${result.updated} 项已写入数据库${correctedCount > 0 ? `，${correctedCount} 项已修正` : ''}`,
          'success',
        )
      }
    } catch (e) {
      showToast(`保存失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <AlertBanner
        variant="info"
        message={'OCR 自动识别的分子结构可能存在错误。下方展示 status=pending 的待复核分子，请逐项核对并矫正。完成时点击『完成矫正』批量保存到数据库。'}
      />
      <CorrectionPanel
        items={items}
        onComplete={handleComplete}
        onItemChange={handleItemChange}
      />
      {saving && (
        <div className="sar-saving-hint">正在批量保存到数据库…</div>
      )}
    </div>
  )
}
