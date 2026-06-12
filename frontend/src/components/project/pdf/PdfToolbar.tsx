import { SearchIcon, CheckIcon, FileTextIcon, LayoutIcon } from '../../icons'
import Toolbar from '../../ui/Toolbar'
import IconButton from '../../ui/IconButton'
import Caption from '../../ui/Caption'
import { ArrowLeftIcon } from '../../icons'
import type { DocumentEntry } from '../../../types'

interface Props {
  doc: DocumentEntry
  onClose: () => void
  pdfScale: number
  onZoomIn: () => void
  onZoomOut: () => void
  onZoomReset: () => void
  currentPage: number
  pdfPageCount: number
  pageJumpInput: string
  onPageJumpInputChange: (v: string) => void
  onJumpToPage: () => void
  onPrevPage: () => void
  onNextPage: () => void
  scrollMode: 'single' | 'continuous'
  onScrollModeChange: (mode: 'single' | 'continuous') => void
  pdfViewMode: 'read' | 'detect' | 'ocr'
  onViewModeChange: (mode: 'read' | 'detect' | 'ocr') => void
  onLoadOcr: () => void
  isLoadingOcr: boolean
  showTextLayer: boolean
  onToggleTextLayer: () => void
  hasTextLayer: boolean
  showTextPanel: boolean
  onToggleTextPanel: () => void
  showImagePanel: boolean
  extractedImagesCount: number
  isLoadingImages: boolean
  onLoadImages: () => void
  pdfOcrSummary: { totalChars: number; textDensity: string } | null
  isDetectMode: boolean
  isDetecting: boolean
  canDetect: boolean
  onDetect: () => void
  currentDetectionsCount: number
}

export default function PdfToolbar(props: Props) {
  const {
    doc, onClose, pdfScale, onZoomIn, onZoomOut, onZoomReset,
    currentPage, pdfPageCount, pageJumpInput, onPageJumpInputChange, onJumpToPage,
    onPrevPage, onNextPage,
    scrollMode, onScrollModeChange,
    pdfViewMode, onViewModeChange, onLoadOcr, isLoadingOcr,
    showTextLayer, onToggleTextLayer, hasTextLayer,
    showTextPanel, onToggleTextPanel,
    showImagePanel, extractedImagesCount, isLoadingImages, onLoadImages,
    pdfOcrSummary,
    isDetectMode, isDetecting, canDetect, onDetect, currentDetectionsCount,
  } = props

  return (
    <Toolbar style={{ justifyContent: 'flex-start', gap: '8px', height: '48px', padding: '0 16px' }}>
      <IconButton size={32} onClick={onClose}>
        <ArrowLeftIcon size={18} />
      </IconButton>
      <Caption truncate style={{ fontSize: '13px', fontWeight: 500, flex: 1 }}>
        {doc.title || doc.path}
      </Caption>

      {/* 缩放控制 */}
      <div className="pdf-zoom-controls">
        <IconButton size={28} onClick={onZoomOut} title="缩小">
          <span style={{ fontSize: '14px', lineHeight: 1 }}>－</span>
        </IconButton>
        <button className="pdf-zoom-reset" onClick={onZoomReset} title="重置缩放">
          {Math.round(pdfScale * 100)}%
        </button>
        <IconButton size={28} onClick={onZoomIn} title="放大">
          <span style={{ fontSize: '14px', lineHeight: 1 }}>＋</span>
        </IconButton>
      </div>

      {/* 分页跳转 */}
      <div className="pdf-page-nav">
        <button className="pdf-page-btn" onClick={onPrevPage} disabled={currentPage <= 1}>←</button>
        <input
          type="text"
          value={pageJumpInput || currentPage}
          onChange={e => onPageJumpInputChange(e.target.value.replace(/\D/g, ''))}
          onKeyDown={e => { if (e.key === 'Enter') onJumpToPage() }}
          onBlur={() => onPageJumpInputChange('')}
          className="pdf-page-input"
        />
        <span className="pdf-page-total">/ {pdfPageCount || '?'}</span>
        <button className="pdf-page-btn" onClick={onNextPage}>→</button>
      </div>

      {/* 滚动模式切换 */}
      {!isDetectMode && pdfViewMode !== 'ocr' && (
        <div className="pdf-segmented">
          <button className={scrollMode === 'continuous' ? 'active' : ''} onClick={() => onScrollModeChange('continuous')} title="连续滚动">
            <LayoutIcon size={11} /> 连续
          </button>
          <button className={scrollMode === 'single' ? 'active' : ''} onClick={() => onScrollModeChange('single')} title="单页">
            <FileTextIcon size={11} /> 单页
          </button>
        </div>
      )}

      {/* 模式切换 */}
      <div className="pdf-segmented">
        <button className={pdfViewMode === 'read' ? 'active' : ''} onClick={() => onViewModeChange('read')}>阅读</button>
        <button className={pdfViewMode === 'detect' ? 'active' : ''} onClick={() => onViewModeChange('detect')}>
          <SearchIcon size={11} /> 分子
        </button>
        <button
          className={pdfViewMode === 'ocr' ? 'active' : ''}
          onClick={() => {
            if (pdfViewMode !== 'ocr') { onViewModeChange('ocr'); onLoadOcr() }
            else { onViewModeChange('read') }
          }}
          disabled={isLoadingOcr}
        >
          {isLoadingOcr ? '加载中...' : 'OCR'}
        </button>
      </div>

      {/* 文本层开关 */}
      <button className={`pdf-tool-btn ${showTextLayer ? 'active' : ''}`} onClick={onToggleTextLayer} disabled={!hasTextLayer}
        title={hasTextLayer ? (showTextLayer ? '隐藏文本层' : '显示文本层') : '此页无文本内容'}>
        {showTextLayer && hasTextLayer ? <CheckIcon size={11} /> : null}
        <span>T</span>
      </button>
      {hasTextLayer && (
        <button className={`pdf-tool-btn ${showTextPanel ? 'active' : ''}`} onClick={onToggleTextPanel} title={showTextPanel ? '关闭文本侧栏' : '打开文本侧栏'}>
          ¶
        </button>
      )}

      {/* 图片提取 */}
      <button className={`pdf-tool-btn ${showImagePanel ? 'active' : ''}`} onClick={onLoadImages} disabled={isLoadingImages}
        title={isLoadingImages ? '提取中...' : (showImagePanel ? '关闭图片面板' : '提取图片')}>
        图片{extractedImagesCount > 0 ? ` ${extractedImagesCount}` : ''}
      </button>

      {/* OCR 状态标识 */}
      {pdfOcrSummary && (
        <span className="pdf-ocr-badge">
          <span className={`pdf-ocr-dot ${pdfOcrSummary.textDensity}`} />
          {pdfOcrSummary.totalChars > 1000
            ? `${(pdfOcrSummary.totalChars / 1000).toFixed(1)}K chars`
            : `${pdfOcrSummary.totalChars} chars`}
        </span>
      )}

      {/* 检测模式：检测按钮 */}
      {isDetectMode && (
        <>
          <button
            className="btn btn-primary pdf-detect-btn"
            onClick={onDetect}
            disabled={isDetecting || !canDetect}
            title={canDetect ? '检测当前页分子' : (currentDetectionsCount > 0 ? '当前页已检测' : '页面渲染中，请稍候')}
          >
            {isDetecting ? '检测中...' : (currentDetectionsCount > 0 ? '已检测' : '检测')}
          </button>
          {currentDetectionsCount > 0 && (
            <span className="pdf-detect-count">{currentDetectionsCount}个</span>
          )}
        </>
      )}
    </Toolbar>
  )
}
