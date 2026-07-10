import { useState, useEffect, useCallback, lazy, Suspense } from 'react'
import { esmilesToMolecode, chemDescriptors } from '@/api/http/molecule'
import { molAdminUpdate } from '@/api/http/molecule_admin'
import { toast } from '@/hooks/useToast'
import type { EvidenceItem, ExtractionResult, MoleculeRecord } from '@/types'
import MoleculeEditorDialog from './MoleculeEditorDialog'
import EvidencePanel from './EvidencePanel'
const MermaidCode = lazy(() =>
  import('@/components/ui/MermaidCode').then(m => ({ default: m.MermaidCode }))
)

interface ChemDescriptors {
  molecular_weight: number
  logp: number
  tpsa: number
  hba: number
  hbd: number
  rotatable_bonds: number
  formula: string
}

const VALID_STATUSES = ['confirmed', 'pending', 'corrected', 'rejected'] as const

interface BaseProps {
  libraryRoot?: string | null
  onOpenPdf?: (docId: string, page: number | null, bbox: EvidenceItem['bbox']) => void
}
interface DetectionProps extends BaseProps {
  detection: ExtractionResult
  index: number
  onSave: (newSmiles: string) => void
  molecule?: never
  onSaved?: never
}

interface MoleculeProps extends BaseProps {
  molecule: MoleculeRecord
  onSaved?: () => void
  detection?: never
  index?: never
  onSave?: never
}

type MoleculeDetailPanelProps = DetectionProps | MoleculeProps

/**
 * 分子详情面板
 *
 * 兼容两种模式：
 * - Detection 模式：展示 ExtractionResult，保留原有编辑按钮与置信度展示。
 * - MoleculeRecord 模式：提供可编辑表单，通过 molAdminUpdate 持久化。
 *
 * 两种模式均显示 MoleCode、理化性质与 E-SMILES。
 */
export default function MoleculeDetailPanel(props: MoleculeDetailPanelProps) {
  const { detection, molecule, libraryRoot } = props
  const isMoleculeMode = Boolean(molecule)

  // Detection 模式：结构编辑器弹窗
  const [showEditor, setShowEditor] = useState(false)

  // MoleculeRecord 模式：本地编辑状态
  const [edited, setEdited] = useState<MoleculeRecord | null>(
    molecule ? { ...molecule } : null
  )
  const [saving, setSaving] = useState(false)

  // 当 molecule 变化时重置表单
  useEffect(() => {
    if (molecule) setEdited({ ...molecule })
  }, [molecule?.mol_id])

  // 用于 MoleCode / descriptors 的当前 E-SMILES 与名称
  const displayEsmiles = isMoleculeMode ? edited?.esmiles : detection?.esmiles
  const displayName = isMoleculeMode ? edited?.name : detection?.name

  const [moleCodeText, setMoleCodeText] = useState<string | null>(null)
  const [moleCodeLoading, setMoleCodeLoading] = useState(false)
  const [descriptors, setDescriptors] = useState<ChemDescriptors | null>(null)
  const [descLoading, setDescLoading] = useState(false)

  // 获取 MoleCode
  useEffect(() => {
    if (!displayEsmiles) return
    setMoleCodeLoading(true)
    esmilesToMolecode(displayEsmiles, displayName || 'Molecule')
      .then(setMoleCodeText)
      .catch(() => setMoleCodeText(null))
      .finally(() => setMoleCodeLoading(false))
  }, [displayEsmiles, displayName])

  // 获取理化性质
  useEffect(() => {
    if (!displayEsmiles) return
    setDescLoading(true)
    chemDescriptors(displayEsmiles)
      .then(setDescriptors)
      .catch(() => setDescriptors(null))
      .finally(() => setDescLoading(false))
  }, [displayEsmiles])

  // Detection 模式：结构编辑器保存回调
  const handleEditorSave = useCallback((newSmiles: string) => {
    if (detection) {
      ;(props).onSave(newSmiles)
      setShowEditor(false)
    }
  }, [detection, props])

  // MoleculeRecord 模式：保存编辑后的记录
  const handleSaveRecord = async () => {
    if (!libraryRoot) {
      toast.error('未指定项目根目录，无法保存')
      return
    }
    if (!edited) return
    setSaving(true)
    try {
      const success = await molAdminUpdate(libraryRoot, edited)
      if (success) {
        toast.success('分子记录已更新')
        ;(props as MoleculeProps).onSaved?.()
      } else {
        toast.error('保存失败')
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleFieldChange = <K extends keyof MoleculeRecord>(
    field: K,
    value: MoleculeRecord[K]
  ) => {
    setEdited(prev => (prev ? { ...prev, [field]: value } : null))
  }

  return (
    <>
      <div
        style={{
          borderTop: '1px solid var(--border)',
          padding: '12px 16px',
          background: 'var(--bg-surface)',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
          maxHeight: '400px',
          overflow: 'auto',
        }}
      >
        {isMoleculeMode && edited ? (
          <MoleculeRecordForm
            record={edited}
            saving={saving}
            onChange={handleFieldChange}
            onSave={handleSaveRecord}
          />
        ) : detection ? (
          <DetectionHeader
            detection={detection}
            index={(props).index}
            onEdit={() => setShowEditor(true)}
          />
        ) : null}

        {/* MoleCode 图（优先显示） */}
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>
            MoleCode
          </div>
          <div
            style={{
              background: 'var(--bg-base)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              padding: 8,
              maxHeight: 150,
              overflow: 'auto',
            }}
          >
            {moleCodeLoading ? (
              <div style={{ textAlign: 'center', padding: 16, color: 'var(--text-muted)', fontSize: 11 }}>
                Loading MoleCode...
              </div>
            ) : moleCodeText ? (
              <Suspense fallback={<div>Loading...</div>}>
                <MermaidCode code={moleCodeText} />
              </Suspense>
            ) : (
              <div style={{ textAlign: 'center', padding: 16, color: 'var(--text-muted)', fontSize: 11 }}>
                无法生成 MoleCode
              </div>
            )}
          </div>
        </div>

        {/* MoleCode 文本 */}
        {moleCodeText && (
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>
              MoleCode 文本
            </div>
            <pre
              style={{
                fontFamily: 'monospace',
                fontSize: 10,
                color: 'var(--text-secondary)',
                background: 'var(--bg-base)',
                padding: '6px 8px',
                borderRadius: 4,
                maxHeight: 100,
                overflow: 'auto',
                margin: 0,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
              }}
            >
              {moleCodeText}
            </pre>
          </div>
        )}

        {/* 理化性质 */}
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>
            理化性质
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: 6,
            }}
          >
            {descLoading ? (
              <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: 8, color: 'var(--text-muted)', fontSize: 11 }}>
                Loading...
              </div>
            ) : descriptors ? (
              <>
                <DescItem label="分子式" value={descriptors.formula} />
                <DescItem label="分子量" value={`${descriptors.molecular_weight.toFixed(1)} g/mol`} />
                <DescItem label="LogP" value={descriptors.logp.toFixed(2)} />
                <DescItem label="TPSA" value={`${descriptors.tpsa.toFixed(1)} Å²`} />
                <DescItem label="HBA" value={String(descriptors.hba)} />
                <DescItem label="HBD" value={String(descriptors.hbd)} />
              </>
            ) : (
              <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: 8, color: 'var(--text-muted)', fontSize: 11 }}>
                无法计算理化性质
              </div>
            )}
          </div>
        </div>

        {/* E-SMILES */}
        {displayEsmiles && (
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>
              E-SMILES
            </div>
            <div
              style={{
                fontFamily: 'monospace',
                fontSize: 11,
                color: 'var(--text-secondary)',
                background: 'var(--bg-base)',
                padding: '6px 8px',
                borderRadius: 4,
                wordBreak: 'break-all',
                maxHeight: 40,
                overflow: 'auto',
              }}
            >
              {displayEsmiles}
            </div>
          </div>
        )}

        {/* MoleculeRecord 模式下的只读元信息 */}
        {isMoleculeMode && molecule && (
          <ReadOnlyMeta record={molecule} />
        )}

        {/* Evidence chain — 列出该分子出现的所有文档/页面位置 */}
        {isMoleculeMode && molecule?.evidence && molecule.evidence.length > 0 && (
          <EvidencePanel
            items={molecule.evidence}
            libraryRoot={libraryRoot ?? null}
            onOpenPdf={(docId, page, bbox) => props.onOpenPdf?.(docId, page, bbox)}
          />
        )}

        {/* Detection 模式下的文献上下文 */}
        {!isMoleculeMode && detection?.context_text && (
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>
              文献上下文
            </div>
            <div
              style={{
                fontSize: 11,
                color: 'var(--text-secondary)',
                background: 'var(--bg-base)',
                padding: '8px 10px',
                borderRadius: 6,
                border: '1px solid var(--border)',
                lineHeight: 1.5,
                maxHeight: 60,
                overflow: 'auto',
              }}
            >
              {detection.context_text}
            </div>
          </div>
        )}
      </div>

      {/* 编辑器浮窗（仅 Detection 模式） */}
      {showEditor && detection && (
        <MoleculeEditorDialog
          smiles={detection.esmiles}
          name={detection.name}
          onSave={handleEditorSave}
          onClose={() => setShowEditor(false)}
        />
      )}
    </>
  )
}

interface DetectionHeaderProps {
  detection: ExtractionResult
  index: number
  onEdit: () => void
}

function DetectionHeader({ detection, index, onEdit }: DetectionHeaderProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ fontSize: '13px', fontWeight: 600 }}>
          分子 #{index + 1}
        </div>
        <div style={{ display: 'flex', gap: '8px', fontSize: '11px', color: 'var(--text-muted)' }}>
          <span>检测: {Math.round(detection.moldet_conf * 100)}%</span>
          <span>识别: {Math.round(detection.scribe_conf * 100)}%</span>
          <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
            综合: {Math.round(detection.composite_conf * 100)}%
          </span>
        </div>
      </div>
      <button
        onClick={onEdit}
        style={{
          padding: '5px 12px',
          background: 'var(--bg-elevated)',
          color: 'var(--text-primary)',
          border: '1px solid var(--border)',
          borderRadius: 6,
          fontSize: 11,
          fontWeight: 500,
          cursor: 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
        }}
      >
        <svg width={11} height={11} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path d="M12 20h9" />
          <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
        </svg>
        编辑
      </button>
    </div>
  )
}

interface MoleculeRecordFormProps {
  record: MoleculeRecord
  saving: boolean
  onChange: <K extends keyof MoleculeRecord>(field: K, value: MoleculeRecord[K]) => void
  onSave: () => void
}

function MoleculeRecordForm({ record, saving, onChange, onSave }: MoleculeRecordFormProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ fontSize: '13px', fontWeight: 600 }}>
          {record.name || record.mol_id}
        </div>
        <button
          onClick={onSave}
          disabled={saving}
          style={{
            padding: '5px 14px',
            background: 'var(--accent)',
            color: '#fff',
            border: 'none',
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 600,
            cursor: saving ? 'not-allowed' : 'pointer',
            opacity: saving ? 0.7 : 1,
          }}
        >
          {saving ? '保存中...' : '保存'}
        </button>
      </div>

      <FormField label="名称">
        <input
          type="text"
          value={record.name || ''}
          onChange={e => onChange('name', e.target.value)}
          style={formInputStyle}
        />
      </FormField>

      <FormField label="E-SMILES">
        <input
          type="text"
          value={record.esmiles}
          onChange={e => onChange('esmiles', e.target.value)}
          style={formInputStyle}
        />
      </FormField>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
        <FormField label="活性">
          <input
            type="number"
            step="any"
            value={record.activity ?? ''}
            onChange={e =>
              onChange('activity', e.target.value === '' ? null : Number(e.target.value))
            }
            style={formInputStyle}
          />
        </FormField>

        <FormField label="活性类型">
          <input
            type="text"
            value={record.activity_type || ''}
            onChange={e => onChange('activity_type', e.target.value)}
            style={formInputStyle}
          />
        </FormField>

        <FormField label="单位">
          <input
            type="text"
            value={record.units || ''}
            onChange={e => onChange('units', e.target.value)}
            style={formInputStyle}
          />
        </FormField>
      </div>

      <FormField label="状态">
        <select
          value={record.status}
          onChange={e => onChange('status', e.target.value)}
          style={formInputStyle}
        >
          {VALID_STATUSES.map(status => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
      </FormField>

      <FormField label="备注">
        <textarea
          value={record.notes || ''}
          onChange={e => onChange('notes', e.target.value)}
          rows={3}
          style={{
            ...formInputStyle,
            resize: 'vertical',
            minHeight: 60,
          }}
        />
      </FormField>
    </div>
  )
}

interface FormFieldProps {
  label: string
  children: React.ReactNode
}

function FormField({ label, children }: FormFieldProps) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)' }}>{label}</span>
      {children}
    </label>
  )
}

const formInputStyle: React.CSSProperties = {
  padding: '6px 10px',
  fontSize: 13,
  borderRadius: 6,
  border: '1px solid var(--border)',
  background: 'var(--bg-base)',
  color: 'var(--text-primary)',
  fontFamily: 'inherit',
  outline: 'none',
}

interface ReadOnlyMetaProps {
  record: MoleculeRecord
}

function ReadOnlyMeta({ record }: ReadOnlyMetaProps) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(2, 1fr)',
        gap: 8,
        padding: '8px 10px',
        background: 'var(--bg-base)',
        borderRadius: 6,
        border: '1px solid var(--border)',
        fontSize: 11,
        color: 'var(--text-muted)',
      }}
    >
      <div>来源文档: {record.source_doc || '-'}</div>
      <div>来源类型: {record.source_type || '-'}</div>
      <div>创建时间: {new Date(record.created_at).toLocaleString()}</div>
      <div>ID: {record.mol_id}</div>
    </div>
  )
}

interface DescItemProps {
  label: string
  value: string
}

function DescItem({ label, value }: DescItemProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
        padding: '4px 6px',
        background: 'var(--bg-base)',
        borderRadius: 4,
        border: '1px solid var(--border)',
      }}
    >
      <div style={{ fontSize: 9, color: 'var(--text-muted)', fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 11, color: 'var(--text-primary)', fontFamily: 'monospace' }}>{value}</div>
    </div>
  )
}
