import { useState, useEffect, useCallback, lazy, Suspense } from 'react'
import { esmilesToMolecode, chemDescriptors } from '../../api/tauri/molecule'
import type { ExtractionResult } from '../../types'
import MoleculeEditorDialog from './MoleculeEditorDialog'

const MermaidCode = lazy(() =>
  import('../ui/MermaidCode').then(m => ({ default: m.MermaidCode }))
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

interface MoleculeDetailPanelProps {
  detection: ExtractionResult
  index: number
  onSave: (newSmiles: string) => void
}

/**
 * 分子详情面板
 *
 * 显示：
 * - MoleCode 图（优先）
 * - 理化性质
 * - 置信度
 * - 文献上下文
 * - 编辑按钮
 */
export default function MoleculeDetailPanel({
  detection,
  index,
  onSave,
}: MoleculeDetailPanelProps) {
  const [showEditor, setShowEditor] = useState(false)
  const [moleCodeText, setMoleCodeText] = useState<string | null>(null)
  const [moleCodeLoading, setMoleCodeLoading] = useState(false)
  const [descriptors, setDescriptors] = useState<ChemDescriptors | null>(null)
  const [descLoading, setDescLoading] = useState(false)

  // 获取 MoleCode
  useEffect(() => {
    if (!detection.esmiles) return
    setMoleCodeLoading(true)
    esmilesToMolecode(detection.esmiles, detection.name || `Mol-${index + 1}`)
      .then(setMoleCodeText)
      .catch(() => setMoleCodeText(null))
      .finally(() => setMoleCodeLoading(false))
  }, [detection.esmiles, detection.name, index])

  // 获取理化性质
  useEffect(() => {
    if (!detection.esmiles) return
    setDescLoading(true)
    chemDescriptors(detection.esmiles)
      .then(setDescriptors)
      .catch(() => setDescriptors(null))
      .finally(() => setDescLoading(false))
  }, [detection.esmiles])

  // 保存回调
  const handleSave = useCallback((newSmiles: string) => {
    onSave(newSmiles)
    setShowEditor(false)
  }, [onSave])

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
        {/* 头部：名称 + 置信度 + 编辑按钮 */}
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
            onClick={() => setShowEditor(true)}
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
            {detection.esmiles}
          </div>
        </div>

        {/* 上下文文本 */}
        {detection.context_text && (
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

      {/* 编辑器浮窗 */}
      {showEditor && (
        <MoleculeEditorDialog
          smiles={detection.esmiles}
          name={detection.name}
          onSave={handleSave}
          onClose={() => setShowEditor(false)}
        />
      )}
    </>
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
