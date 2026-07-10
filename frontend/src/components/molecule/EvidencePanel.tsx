import type { EvidenceItem } from '@/types'

interface EvidencePanelProps {
  items: EvidenceItem[]
  libraryRoot: string | null
  /** Called when the user clicks "打开原文" on a row. */
  onOpenPdf: (docId: string, page: number | null, bbox: EvidenceItem['bbox']) => void
}

/**
 * Vertical list of evidence rows for a single molecule.
 *
 * Each row shows: a 48x48 thumbnail (figure kind only), the document id,
 * the page number, and a "打开原文" button. The full-chain view is used in
 * the MoleculeDetailDrawer; the list view in the library table truncates
 * to 50 items.
 */
export default function EvidencePanel({ items, libraryRoot, onOpenPdf }: EvidencePanelProps) {
  if (!items || items.length === 0) {
    return null
  }
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        padding: '10px 12px',
        background: 'var(--bg-base)',
        border: '1px solid var(--border)',
        borderRadius: 8,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 4,
        }}
      >
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)' }}>
          证据链 · {items.length} 处
        </div>
      </div>
      {items.map((ev) => (
        <EvidenceRow
          key={ev.id}
          ev={ev}
          libraryRoot={libraryRoot}
          onOpenPdf={onOpenPdf}
        />
      ))}
    </div>
  )
}

interface RowProps {
  ev: EvidenceItem
  libraryRoot: string | null
  onOpenPdf: EvidencePanelProps['onOpenPdf']
}

function EvidenceRow({ ev, libraryRoot, onOpenPdf }: RowProps) {
  const kindLabel = ev.kind === 'figure' ? '图' : ev.kind === 'text' ? '文' : '表'
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '6px 8px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 6,
        fontSize: 12,
      }}
    >
      {ev.kind === 'figure' && ev.crop_url ? (
        <img
          src={ev.crop_url}
          alt={`${ev.doc_id} crop`}
          style={{
            width: 48,
            height: 48,
            objectFit: 'contain',
            background: '#fff',
            border: '1px solid var(--border)',
            borderRadius: 4,
            flexShrink: 0,
          }}
          loading="lazy"
        />
      ) : (
        <div
          style={{
            width: 48,
            height: 48,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'var(--bg-base)',
            border: '1px solid var(--border)',
            borderRadius: 4,
            fontSize: 18,
            color: 'var(--text-muted)',
            flexShrink: 0,
          }}
        >
          {kindLabel}
        </div>
      )}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
        <div
          style={{
            fontSize: 12,
            fontWeight: 500,
            color: 'var(--text-primary)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          title={ev.doc_id}
        >
          {ev.doc_id}
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
          {ev.kind === 'figure' && ev.page != null ? `第 ${ev.page} 页` : null}
          {ev.kind === 'text' ? '文本提及' : null}
          {ev.kind === 'table' ? '表格' : null}
          {ev.confidence != null ? ` · 置信度 ${(ev.confidence * 100).toFixed(0)}%` : null}
        </div>
      </div>
      <button
        type="button"
        onClick={() => onOpenPdf(ev.doc_id, ev.page, ev.bbox)}
        disabled={!libraryRoot}
        title={!libraryRoot ? 'library_root 未配置' : '在 PDF 查看器中打开'}
        style={{
          padding: '4px 10px',
          fontSize: 11,
          fontWeight: 600,
          background: 'var(--accent)',
          color: '#fff',
          border: 'none',
          borderRadius: 4,
          cursor: libraryRoot ? 'pointer' : 'not-allowed',
          opacity: libraryRoot ? 1 : 0.5,
          flexShrink: 0,
        }}
      >
        打开原文
      </button>
    </div>
  )
}
