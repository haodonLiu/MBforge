import PdfCanvas from '../PdfCanvas'
import PdfContinuousViewer from '../PdfContinuousViewer'
import MoleculeOverlay from '../MoleculeOverlay'
import OcrOverlay from '../OcrOverlay'
import ScrollColumn from '../ui/ScrollColumn'
import Spinner from '../ui/Spinner'
import type { DocumentEntry } from '../../types'
import { usePdfViewer } from './pdf/usePdfViewer'
import { useIngestPipeline } from './pdf/useIngestPipeline'
import PdfToolbar from './pdf/PdfToolbar'
import PdfFloatingControls from './pdf/PdfFloatingControls'
import PdfResultPane from './pdf/PdfResultPane'
import PdfPipelineFlow from './pdf/PdfPipelineFlow'
import { OcrPanel } from './pdf/PdfViewerPanels'

interface Props {
  doc: DocumentEntry
  projectRoot: string
  onClose: () => void
  initialMode?: 'read' | 'detect' | 'ocr'
}

export default function PdfViewer({ doc, projectRoot, onClose, initialMode }: Props) {
  const v = usePdfViewer(doc, projectRoot, initialMode)
  const pipeline = useIngestPipeline(doc.doc_id, projectRoot)

  return (
    <div className="pdf-viewer">
      {pipeline.task && pipeline.task.status !== 'done' && pipeline.task.status !== 'cancelled' && (
        <PdfPipelineFlow
          variant="full"
          task={pipeline.task}
          progressPct={pipeline.progressPct}
          details={pipeline.details}
          embedState={pipeline.embedState}
        />
      )}
      <PdfToolbar
        doc={doc}
        onClose={onClose}
        pdfViewMode={v.pdfViewMode}
        onViewModeChange={v.setPdfViewMode}
        onLoadOcr={v.handleLoadOcr}
        isLoadingOcr={v.isLoadingOcr}
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
        isDetectMode={v.isDetectMode}
        isDetecting={v.isDetecting}
        canDetect={v.canDetect}
        onDetect={() => v.handleDetectPage(true)}
        onClearDetectionCache={v.handleClearDetectionCache}
        currentDetectionsCount={v.currentDetections.length}
        confidenceThreshold={v.confidenceThreshold}
        onConfidenceThresholdChange={v.setConfidenceThreshold}
      />

      <div className="pdf-dual-pane">
        {/* 左侧：PDF 内容 */}
        <div className="pdf-source-pane">
          {v.isSinglePageMode ? (
            <ScrollColumn
              ref={v.pdfScrollRef}
              tabIndex={0}
              onKeyDown={v.handleKeyDown}
              onWheel={v.handleWheel}
              className="pdf-single-page"
              style={{
                background: 'var(--bg-base)',
                padding: v.isDetectMode || v.isOcrMode ? '20px' : '0',
              }}
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
                    generateImage={v.isDetectMode}
                    showTextLayer={v.showTextLayer && v.hasTextLayer}
                    onPageRendered={v.handlePageRendered}
                    onImageReady={v.handleImageReady}
                    onTextContent={v.handleTextContent}
                    onTextLayerClick={() => v.setShowTextPanel(true)}
                    onPageCount={v.handlePageCount}
                    style={{
                      background: '#fff',
                      boxShadow: v.isDetectMode ? '0 2px 12px rgba(0,0,0,0.15)' : 'none',
                    }}
                  />
                )}
                {v.isDetectMode && v.pageInfo && v.currentDetections.length > 0 && (
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
                {v.isOcrMode && v.pageInfo && v.ocrBlocks.length > 0 && (
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
              </div>
            </ScrollColumn>
          ) : (
            <div className="pdf-continuous" style={{ background: 'var(--bg-base)' }}>
              {v.pdfLoading || !v.pdfUrl ? (
                <div className="pdf-loading">
                  <Spinner size={32} />
                  <div className="pdf-loading-title">{doc.title || doc.path.split(/[\\/]/).pop()}</div>
                  <div className="pdf-loading-sub">读取文件中，请稍候…</div>
                </div>
              ) : (
                <PdfContinuousViewer
                  ref={v.pdfScrollRef}
                  url={v.pdfUrl}
                  scale={v.pdfScale}
                  onPageChange={v.setCurrentPage}
                  onPageCount={v.handlePageCount}
                />
              )}
            </div>
          )}

          {/* 底部浮动控件 */}
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

        {/* 右侧：识别结果面板 */}
        <PdfResultPane
          currentPage={v.currentPage}
          currentTextItems={v.currentTextItems}
          currentTextTotal={v.currentTextTotal}
          detections={v.currentDetections}
          selectedDetection={v.selectedDetection}
          onSelectDetection={v.setSelectedDetection}
          onScrollToDetection={v.scrollToDetection}
          confidenceThreshold={v.confidenceThreshold}
        />
      </div>

      {/* OCR 结果面板（保留，仅在 OCR 模式显示） */}
      {v.showOcrPanel && (
        <OcrPanel
          blocks={v.ocrBlocks}
          currentPage={v.currentPage}
          selectedIndex={v.selectedOcrIndex}
          hoveredIndex={v.hoveredOcrIndex}
          onSelect={(index) => {
            const block = v.ocrBlocks[index]
            if (!block) return
            const needPageChange = block.page !== v.currentPage
            if (needPageChange) v.setCurrentPage(block.page)
            v.setSelectedOcrIndex(index)
            const doScroll = () => {
              const info = v.pageInfoRef.current
              const container = v.pdfScrollRef.current
              if (!info || !container) return
              const [, , , y2] = block.bbox
              const cssY = (info.originalHeight - y2) * info.scale
              container.scrollTo({ top: Math.max(0, cssY - 40), behavior: 'smooth' })
            }
            needPageChange ? setTimeout(doScroll, 300) : doScroll()
          }}
          onClose={() => v.setShowOcrPanel(false)}
        />
      )}
    </div>
  )
}
