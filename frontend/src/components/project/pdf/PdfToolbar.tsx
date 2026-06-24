import { SearchIcon, CheckIcon, ArrowLeftIcon } from '../../icons'
import IconButton from '../../ui/IconButton'
import Caption from '../../ui/Caption'
import type { DocumentEntry } from '../../../types'

interface Props {
  doc: DocumentEntry
  onClose: () => void
  pdfViewMode: 'read' | 'detect' | 'ocr' | 'coref'
  onViewModeChange: (mode: 'read' | 'detect' | 'ocr' | 'coref') => void
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
  onClearDetectionCache: () => void
  currentDetectionsCount: number
  confidenceThreshold: number
  onConfidenceThresholdChange: (threshold: number) => void
  /** coref 模式专属 */
  isCorefMode?: boolean
  isLoadingCoref?: boolean
  corefLabelsCount?: number
  corefPredictionsCount?: number
  corefThreshold?: number
  onCorefThresholdChange?: (threshold: number) => void
  onRefreshCoref?: () => void
}

export default function PdfToolbar(props: Props) {
  const {
    doc, onClose,
    pdfViewMode, onViewModeChange, onLoadOcr, isLoadingOcr,
    showTextLayer, onToggleTextLayer, hasTextLayer,
    showTextPanel, onToggleTextPanel,
    showImagePanel, extractedImagesCount, isLoadingImages, onLoadImages,
    pdfOcrSummary,
    isDetectMode, isDetecting, canDetect, onDetect, onClearDetectionCache, currentDetectionsCount,
    confidenceThreshold, onConfidenceThresholdChange,
    isCorefMode, isLoadingCoref, corefLabelsCount, corefPredictionsCount,
    corefThreshold, onCorefThresholdChange, onRefreshCoref,
  } = props

  return (
    <div className="pdf-toolbar">
      <div className="pdf-toolbar-left">
        <IconButton size={28} onClick={onClose} title="返回">
          <ArrowLeftIcon size={16} />
        </IconButton>
        <Caption truncate style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)' }}>
          {doc.title || doc.path}
        </Caption>
      </div>

      <div className="pdf-toolbar-right">
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
          <button
            className={pdfViewMode === 'coref' ? 'active' : ''}
            onClick={() => onViewModeChange(pdfViewMode === 'coref' ? 'read' : 'coref')}
            disabled={isLoadingCoref}
            title="分子 ↔ 标识符 共指标注（增强专利 PDF 检索）"
          >
            {isLoadingCoref ? '加载中...' : '共指'}
            {isCorefMode && (corefPredictionsCount ?? 0) > 0 && (
              <span style={{ marginLeft: 4, fontSize: 10, opacity: 0.7 }}>{corefPredictionsCount}</span>
            )}
          </button>
        </div>

        <div className="pdf-toolbar-sep" />

        {/* 工具按钮组 */}
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
              title={canDetect ? (currentDetectionsCount > 0 ? '重新检测当前页分子' : '检测当前页分子') : '页面渲染中，请稍候'}
            >
              {isDetecting ? '检测中...' : (currentDetectionsCount > 0 ? '重新检测' : '检测')}
            </button>
            {currentDetectionsCount > 0 && (
              <span className="pdf-detect-count">{currentDetectionsCount}个</span>
            )}
            <button
              className="btn btn-secondary pdf-detect-btn"
              onClick={onClearDetectionCache}
              disabled={isDetecting}
              title="清除该文档全部分子识别缓存"
            >
              清除缓存
            </button>

            {/* 置信度阈值控制 */}
            <div className="pdf-toolbar-sep" />
            <div className="pdf-confidence-control">
              <span className="pdf-confidence-label">置信度</span>
              <input
                type="range"
                min="0"
                max="100"
                value={Math.round(confidenceThreshold * 100)}
                onChange={e => onConfidenceThresholdChange(Number(e.target.value) / 100)}
                className="pdf-confidence-slider"
              />
              <span className="pdf-confidence-value">{Math.round(confidenceThreshold * 100)}%</span>
            </div>
          </>
        )}

        {/* coref 模式：阈值 + 计数 + 刷新 */}
        {isCorefMode && (
          <>
            <div className="pdf-toolbar-sep" />
            <div className="pdf-confidence-control">
              <span className="pdf-confidence-label">配对阈值</span>
              <input
                type="range"
                min="0"
                max="100"
                value={Math.round((corefThreshold ?? 0.3) * 100)}
                onChange={e => onCorefThresholdChange?.(Number(e.target.value) / 100)}
                className="pdf-confidence-slider"
                title="置信度阈值：低于此值的共指配对不显示"
              />
              <span className="pdf-confidence-value">{Math.round((corefThreshold ?? 0.3) * 100)}%</span>
            </div>
            <span className="pdf-detect-count" title="label / 配对 数量">
              {corefLabelsCount ?? 0}标 / {corefPredictionsCount ?? 0}配
            </span>
            <button
              className="btn btn-secondary pdf-detect-btn"
              onClick={onRefreshCoref}
              disabled={isLoadingCoref}
              title="从 KB 重新加载当前页 coref 数据"
            >
              刷新
            </button>
          </>
        )}
      </div>
    </div>
  )
}
