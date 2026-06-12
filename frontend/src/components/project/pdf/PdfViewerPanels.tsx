import ScrollColumn from '../../ui/ScrollColumn'
import MoleculeDetailPanel from '../../molecule/MoleculeDetailPanel'
import OcrResultPanel from '../../OcrResultPanel'
import type { ExtractionResult } from '../../../types'
import type { ImageRef, OcrBlock } from '../../../api/tauri/pdf'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'

// ============================================================================
// 文本面板
// ============================================================================

interface TextPanelProps {
  currentPage: number
  currentTextItems: { str: string; x: number; y: number; width: number; height: number }[]
  currentTextTotal: number
  onClose: () => void
}

function itemsToMarkdown(items: { str: string; x: number; y: number; width: number; height: number }[]): string {
  if (items.length === 0) return ''
  const sorted = [...items].sort((a, b) => {
    const dy = a.y - b.y
    if (Math.abs(dy) > 3) return dy
    return a.x - b.x
  })
  const lines: string[][] = []
  let currentLine: string[] = []
  let currentY = sorted[0].y
  for (const item of sorted) {
    if (Math.abs(item.y - currentY) > 6) {
      if (currentLine.length > 0) lines.push(currentLine)
      currentLine = [item.str]
      currentY = item.y
    } else {
      currentLine.push(item.str)
    }
  }
  if (currentLine.length > 0) lines.push(currentLine)
  return lines.map(line => line.join(' ').trim()).join('\n\n')
}

export function TextPanel({ currentPage, currentTextItems, currentTextTotal, onClose }: TextPanelProps) {
  const markdown = itemsToMarkdown(currentTextItems)
  return (
    <div className="pdf-side-panel">
      <div className="pdf-side-panel-header">
        <span>第 {currentPage} 页文本</span>
        <button className="pdf-side-panel-close" onClick={onClose}>✕</button>
      </div>
      <ScrollColumn className="pdf-text-content markdown-preview">
        {currentTextItems.length === 0 ? (
          <span className="pdf-panel-empty">当前页无文本内容</span>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
            {markdown}
          </ReactMarkdown>
        )}
      </ScrollColumn>
      <div className="pdf-text-footer">
        <span>{currentTextItems.length} 段</span>
        <span>{currentTextTotal} 字符</span>
      </div>
    </div>
  )
}

// ============================================================================
// 图片面板
// ============================================================================

interface ImagePanelProps {
  images: ImageRef[]
  imageBlobUrls: Map<string, string>
  isLoading: boolean
  onClose: () => void
}

export function ImagePanel({ images, imageBlobUrls, isLoading, onClose }: ImagePanelProps) {
  return (
    <div className="pdf-side-panel" style={{ width: '300px' }}>
      <div className="pdf-side-panel-header">
        <span>提取图片 ({images.length})</span>
        <button className="pdf-side-panel-close" onClick={onClose}>✕</button>
      </div>
      <ScrollColumn className="pdf-image-list">
        {images.length === 0 && (
          <span className="pdf-panel-empty">{isLoading ? '提取中...' : '未提取到图片'}</span>
        )}
        {images.map((img, idx) => {
          const imgUrl = img.rel_path ? (imageBlobUrls.get(img.rel_path) ?? '') : ''
          return (
            <div key={idx} className="pdf-image-card">
              {imgUrl && (
                <img src={imgUrl} alt={img.filename} className="pdf-image-thumb" loading="lazy" />
              )}
              <div className="pdf-image-meta">
                <div className="pdf-image-meta-row">
                  <span>第 {img.page} 页</span>
                  {img.esmiles && <span className="pdf-image-smiles">SMILES</span>}
                </div>
                {img.description && <div className="pdf-image-desc">{img.description}</div>}
                {!img.description && !img.esmiles && (
                  <div className="pdf-image-no-desc">暂无描述</div>
                )}
              </div>
            </div>
          )
        })}
      </ScrollColumn>
    </div>
  )
}

// ============================================================================
// OCR 结果面板
// ============================================================================

interface OcrPanelProps {
  blocks: OcrBlock[]
  currentPage: number
  selectedIndex: number | null
  hoveredIndex: number | null
  onSelect: (index: number) => void
  onClose: () => void
}

export function OcrPanel({ blocks, currentPage, selectedIndex, hoveredIndex, onSelect, onClose }: OcrPanelProps) {
  return (
    <OcrResultPanel
      blocks={blocks}
      currentPage={currentPage}
      selectedIndex={selectedIndex ?? null}
      hoveredIndex={hoveredIndex ?? null}
      onSelect={onSelect}
      onClose={onClose}
    />
  )
}

// ============================================================================
// 检测详情面板
// ============================================================================

interface DetectDetailPanelProps {
  detection: ExtractionResult | undefined
  index: number
  onSave: (newSmiles: string) => void
  onClose: () => void
}

export function DetectDetailPanel({ detection, index, onSave, onClose }: DetectDetailPanelProps) {
  if (!detection) return null
  return (
    <div className="pdf-side-panel" style={{ width: '320px' }}>
      <div className="pdf-side-panel-header">
        <span>分子详情</span>
        <button className="pdf-side-panel-close" onClick={onClose}>✕</button>
      </div>
      <ScrollColumn style={{ padding: 0 }}>
        <MoleculeDetailPanel detection={detection} index={index} onSave={onSave} />
      </ScrollColumn>
    </div>
  )
}
