import { forwardRef, useCallback, useEffect, useImperativeHandle, useState } from 'react'
import PdfCanvas from '@/components/PdfCanvas'
import MoleculeOverlay from '@/components/MoleculeOverlay'
import OcrOverlay from '@/components/OcrOverlay'
import CorefBboxOverlay, { type MolClickInfo } from './pdf/CorefBboxOverlay'
import ScrollColumn from '../ui/ScrollColumn'
import Spinner from '../ui/Spinner'
import type { DocumentEntry, ExtractionResult } from '@/types'
import { usePdfViewer } from './pdf/usePdfViewer'
import { useIngestPipeline } from './pdf/useIngestPipeline'
import PdfToolbar from './pdf/PdfToolbar'
import PdfFloatingControls from './pdf/PdfFloatingControls'
import PdfResultPane from './pdf/PdfResultPane'
import PdfPipelineFlow from './pdf/PdfPipelineFlow'
import { updateCorefPair, confirmCorefPrediction } from '@/api/http/result_pane'
import type { FigureLabel, CorefPrediction } from '@/api/http/result_pane'
import { showToast } from '@/hooks/useToast'

/** Imperative handle exposed to a parent (DocumentViewer). */
export interface PdfViewerHandle {
  setCurrentPage: (page: number) => void
  scrollToDetection: (detection: ExtractionResult) => void
}

interface Props {
  doc: DocumentEntry
  libraryRoot: string
  onClose: () => void
}

interface CorefContextMenu {
  clickInfo: MolClickInfo
  x: number
  y: number
}

function parseImageBasename(p: string | null | undefined): { page: number; imgIdx: number } | null {
  if (!p) return null
  const m = /page[_-](\d+)[_-]img[_-](\d+)/i.exec(p.split(/[\\/]/).pop() ?? '')
  if (!m) return null
  return { page: parseInt(m[1], 10), imgIdx: parseInt(m[2], 10) }
}

function buildFigureBoxesForPage(
  allBoxes: Map<string, [number, number, number, number]>,
  labels: FigureLabel[],
  predictions: CorefPrediction[],
  currentPage: number,
): Map<string, [number, number, number, number]> {
  const out = new Map<string, [number, number, number, number]>()
  const needImagePaths = new Set<string>()
  for (const l of labels) if (l.image_path) needImagePaths.add(l.image_path)
  for (const p of predictions) if (p.image_path) needImagePaths.add(p.image_path)

  for (const path of needImagePaths) {
    const parsed = parseImageBasename(path)
    if (!parsed) continue
    if (parsed.page !== currentPage) continue
    const orderKey = `__order__:${parsed.page}:${parsed.imgIdx}`
    const bbox = allBoxes.get(orderKey)
    if (bbox) {
      out.set(path.split(/[\\/]/).pop() ?? path, bbox)
    }
  }
  return out
}

const PdfViewer = forwardRef<PdfViewerHandle, Props>(function PdfViewer(
  { doc, libraryRoot, onClose },
  ref,
) {
  const v = usePdfViewer(doc, libraryRoot)
  const pipeline = useIngestPipeline(doc.doc_id, libraryRoot)
  const [corefMenu, setCorefMenu] = useState<CorefContextMenu | null>(null)

  useImperativeHandle(ref, () => ({
    setCurrentPage: (page: number) => v.setCurrentPage(page),
    scrollToDetection: (detection: ExtractionResult) => v.scrollToDetection(detection),
  }), [v])

  useEffect(() => {
    if (!corefMenu) return
    const onDown = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null
      if (target?.closest('.coref-context-menu')) return
      setCorefMenu(null)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setCorefMenu(null)
    }
    window.addEventListener('mousedown', onDown)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [corefMenu])

  const handleMolClick = useCallback((info: MolClickInfo) => {
    setCorefMenu({
      clickInfo: info,
      x: window.innerWidth / 2,
      y: window.innerHeight / 2,
    })
  }, [])

  const handleMolContextMenu = useCallback((info: MolClickInfo, e: React.MouseEvent) => {
    e.preventDefault()
    setCorefMenu({ clickInfo: info, x: e.clientX, y: e.clientY })
  }, [])

  const handlePickLabel = useCallback(async (label: FigureLabel) => {
    if (!corefMenu) return
    const { prediction } = corefMenu.clickInfo
    setCorefMenu(null)
    try {
      await updateCorefPair(
        libraryRoot,
        doc.doc_id,
        v.currentPage,
        prediction.id,
        null,
        prediction.mol_smiles,
        prediction.mol_bbox,
        label.id,
      )
      showToast(`已重选 → ${label.label_text}`, 'success')
      void v.refreshCorefForPage()
    } catch (e) {
      showToast('重选 coref 失败：' + (e instanceof Error ? e.message : String(e)), 'error')
    }
  }, [libraryRoot, doc.doc_id, v])

  const handleConfirm = useCallback(async (p: CorefPrediction, confirmed: boolean) => {
    setCorefMenu(null)
    try {
      await confirmCorefPrediction(libraryRoot, p.id, confirmed)
      showToast(confirmed ? '已确认' : '已撤销', 'success')
      void v.refreshCorefForPage()
    } catch (e) {
      showToast('操作失败：' + (e instanceof Error ? e.message : String(e)), 'error')
    }
  }, [libraryRoot, v])

  return (
    <div className="pdf-viewer">
      {pipeline.task && pipeline.task.status !== 'done' && pipeline.task.status !== 'cancelled' && (
        <PdfPipelineFlow
          variant="full"
          task={pipeline.task}
          progressPct={pipeline.progressPct}
          details={pipeline.details}
        />
      )}
      <PdfToolbar
        doc={doc}
        onClose={onClose}
        showTextLayer={v.showTextLayer}
        onToggleTextLayer={() => v.setShowTextLayer(!v.showTextLayer)}
        hasTextLayer={v.hasTextLayer}
        showTextPanel={v.showTextPanel}
        onToggleTextPanel={() => v.setShowTextPanel(!v.showTextPanel)}
        showImagePanel={v.showImagePanel}
        extractedImagesCount={v.extractedImages.length}
        isLoadingImages={v.isLoadingImages}
        onLoadImages={v.handleLoadImages}
        pdfOcrSummary={v.pdfOcrSummary}
        isDetecting={v.isDetecting}
        canDetect={v.canDetect}
        onDetect={() => v.handleDetectPage(true)}
        onClearDetectionCache={v.handleClearDetectionCache}
        currentDetectionsCount={v.currentDetections.length}
        confidenceThreshold={v.confidenceThreshold}
        onConfidenceThresholdChange={v.setConfidenceThreshold}
        isLoadingCoref={v.isLoadingCoref}
        corefLabelsCount={v.corefLabels.length}
        corefPredictionsCount={v.corefPredictions.length}
        corefThreshold={v.corefThreshold}
        onCorefThresholdChange={v.setCorefThreshold}
        onRefreshCoref={v.refreshCorefForPage}
      />

      <div className="pdf-dual-pane">
        {/* 左侧：PDF 内容 + 所有 bbox overlay */}
        <div className="pdf-source-pane">
          <ScrollColumn
            ref={v.pdfScrollRef}
            tabIndex={0}
            onKeyDown={v.handleKeyDown}
            onWheel={v.handleWheel}
            className="pdf-single-page"
            style={{ background: 'var(--bg-base)', padding: '20px' }}
          >
            <div className="pdf-canvas-wrap">
              {v.pdfLoading || !v.pdfUrl ? (
                <div className="pdf-loading">
                  <Spinner size={32} />
                  <div className="pdf-loading-title">{doc.title || doc.path.split(/[\\/]/).pop()}</div>
                  <div className="pdf-loading-sub">读取文件中，请稍候…</div>
                </div>
              ) : (
                <PdfCanvas
                  url={v.pdfUrl}
                  pageNumber={v.currentPage}
                  scale={v.pdfScale}
                  generateImage
                  showTextLayer={v.showTextLayer && v.hasTextLayer}
                  onPageRendered={v.handlePageRendered}
                  onImageReady={v.handleImageReady}
                  onTextContent={v.handleTextContent}
                  onTextLayerClick={() => v.setShowTextPanel(true)}
                  onPageCount={v.handlePageCount}
                  style={{ background: '#fff', boxShadow: '0 2px 12px rgba(0,0,0,0.15)' }}
                />
              )}
              {v.pageInfo && v.currentDetections.length > 0 && (
                <MoleculeOverlay
                  detections={v.currentDetections}
                  renderWidth={v.pageInfo.width}
                  renderHeight={v.pageInfo.height}
                  originalHeight={v.pageInfo.originalHeight}
                  scale={v.pageInfo.scale}
                  currentPage={v.currentPage}
                  selectedIndex={v.selectedDetection ?? undefined}
                  onSelect={v.setSelectedDetection}
                  onRecognize={v.handleRecognizePage}
                  isRecognizing={v.isDetecting}
                />
              )}
              {v.pageInfo && v.ocrBlocks.length > 0 && (
                <OcrOverlay
                  blocks={v.ocrBlocks}
                  renderWidth={v.pageInfo.width}
                  renderHeight={v.pageInfo.height}
                  originalHeight={v.pageInfo.originalHeight}
                  scale={v.pageInfo.scale}
                  page={v.currentPage}
                  selectedIndex={v.selectedOcrIndex ?? undefined}
                  onSelect={v.setSelectedOcrIndex}
                  onHover={v.setHoveredOcrIndex}
                />
              )}
              {v.pageInfo && (
                <CorefBboxOverlay
                  labels={v.corefLabels}
                  predictions={v.corefPredictions}
                  threshold={v.corefThreshold}
                  containerWidth={v.pageInfo.width}
                  containerHeight={v.pageInfo.height}
                  originalHeight={v.pageInfo.originalHeight}
                  scale={v.pageInfo.scale}
                  figureBoxes={buildFigureBoxesForPage(
                    v.corefFigureBoxes,
                    v.corefLabels,
                    v.corefPredictions,
                    v.currentPage,
                  )}
                  onMolClick={handleMolClick}
                  onMolContextMenu={handleMolContextMenu}
                  onLabelClick={() => {}}
                />
              )}
            </div>
          </ScrollColumn>

          <PdfFloatingControls
            pdfScale={v.pdfScale}
            onZoomIn={v.handleZoomIn}
            onZoomOut={v.handleZoomOut}
            onZoomReset={v.handleZoomReset}
            currentPage={v.currentPage}
            pdfPageCount={v.pdfPageCount}
            pageJumpInput={v.pageJumpInput}
            onPageJumpInputChange={v.setPageJumpInput}
            onJumpToPage={v.handleJumpToPage}
            onPrevPage={() => { v.setCurrentPage(p => Math.max(1, p - 1)); v.setSelectedDetection(null) }}
            onNextPage={() => v.setCurrentPage(p => p + 1)}
          />
        </div>

        {/* 右侧：文本+分子合并视图（OCR bbox 用于文本段落分组） */}
        <PdfResultPane
          currentPage={v.currentPage}
          currentTextItems={v.currentTextItems}
          currentTextTotal={v.currentTextTotal}
          detections={v.currentDetections}
          selectedDetection={v.selectedDetection}
          onSelectDetection={v.setSelectedDetection}
          onScrollToDetection={v.scrollToDetection}
          confidenceThreshold={v.confidenceThreshold}
          ocrBlocks={v.ocrBlocks}
        />
      </div>

      {/* Coref 右键菜单 */}
      {corefMenu && (
        <div
          className="coref-context-menu"
          style={{
            position: 'fixed',
            left: corefMenu.x,
            top: corefMenu.y,
            background: 'var(--bg-elevated, #1e1e1e)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
            padding: 6,
            minWidth: 220,
            zIndex: 1000,
            fontSize: 12,
            color: 'var(--text-primary)',
          }}
          onContextMenu={e => e.preventDefault()}
        >
          <div style={{ padding: '4px 8px', opacity: 0.7, borderBottom: '1px solid var(--border)', marginBottom: 4 }}>
            分子：{corefMenu.clickInfo.prediction.mol_smiles ?? '(no SMILES)'}
            <br />
            置信度：{(corefMenu.clickInfo.prediction.confidence * 100).toFixed(0)}%
            （source={corefMenu.clickInfo.prediction.source}）
          </div>
          <button
            className="pdf-tool-btn"
            style={{ display: 'block', width: '100%', textAlign: 'left', padding: '4px 8px', background: 'transparent', border: 'none', cursor: 'pointer', color: 'inherit' }}
            onClick={() => handleConfirm(corefMenu.clickInfo.prediction, !corefMenu.clickInfo.prediction.is_confirmed)}
          >
            {corefMenu.clickInfo.prediction.is_confirmed ? '撤销确认' : '✓ 确认此配对'}
          </button>
          <div style={{ padding: '4px 8px', opacity: 0.6, marginTop: 4 }}>重选 coref（点击 label）：</div>
          <div style={{ maxHeight: 220, overflowY: 'auto' }}>
            {v.corefLabels.length === 0 && (
              <div style={{ padding: '4px 8px', opacity: 0.5 }}>当前页无 label</div>
            )}
            {v.corefLabels
              .filter(l => !corefMenu.clickInfo.pairedLabels.some(p => p.id === l.id))
              .map(l => (
                <button
                  key={l.id}
                  className="pdf-tool-btn"
                  style={{ display: 'block', width: '100%', textAlign: 'left', padding: '4px 8px', background: 'transparent', border: 'none', cursor: 'pointer', color: 'inherit', fontFamily: 'monospace' }}
                  onClick={() => handlePickLabel(l)}
                  title={`OCR conf=${l.ocr_conf.toFixed(2)}`}
                >
                  → {l.label_text}
                </button>
              ))}
          </div>
          <div style={{ padding: '4px 8px', opacity: 0.5, marginTop: 4, fontSize: 10 }}>
            左键点击分子框：选中/取消选中
          </div>
        </div>
      )}
    </div>
  )
})

export default PdfViewer
