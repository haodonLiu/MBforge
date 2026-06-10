import PdfCanvas from '../PdfCanvas'
import PdfContinuousViewer from '../PdfContinuousViewer'
import MoleculeOverlay from '../MoleculeOverlay'
import OcrOverlay from '../OcrOverlay'
import ScrollColumn from '../ui/ScrollColumn'
import Spinner from '../ui/Spinner'
import type { DocumentEntry } from '../../types'
import { usePdfViewer } from './pdf/usePdfViewer'
import PdfToolbar from './pdf/PdfToolbar'
import { TextPanel, ImagePanel, OcrPanel, DetectDetailPanel } from './pdf/PdfViewerPanels'

interface Props {
  doc: DocumentEntry
  projectRoot: string
  onClose: () => void
  initialMode?: 'read' | 'detect' | 'ocr'
}

export default function PdfViewer({ doc, projectRoot, onClose, initialMode }: Props) {
  const v = usePdfViewer(doc, projectRoot, initialMode)

  return (
    <div className="pdf-viewer">
      <PdfToolbar
        doc={doc}
        onClose={onClose}
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
        scrollMode={v.scrollMode}
        onScrollModeChange={v.setScrollMode}
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
        onDetect={v.handleDetectPage}
        currentDetectionsCount={v.currentDetections.length}
      />

      <div className="pdf-main">
        {/* PDF 内容 */}
        {v.isSinglePageMode ? (
          <ScrollColumn
            ref={v.pdfScrollRef}
            tabIndex={0}
            onKeyDown={v.handleKeyDown}
            onWheel={v.handleWheel}
            className="pdf-single-page"
            style={{
              background: v.isDetectMode || v.isOcrMode ? 'var(--bg-base)' : '#525659',
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
                  selectedIndex={v.selectedDetection ?? undefined}
                  onSelect={v.setSelectedDetection}
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
          <div className="pdf-continuous" style={{ background: '#525659' }}>
            {v.pdfLoading || !v.pdfUrl ? (
              <div className="pdf-loading">
                <Spinner size={32} />
                <div className="pdf-loading-title">{doc.title || doc.path.split(/[\\/]/).pop()}</div>
                <div className="pdf-loading-sub">读取文件中，请稍候…</div>
              </div>
            ) : (
              <PdfContinuousViewer
                url={v.pdfUrl}
                scale={v.pdfScale}
                onPageChange={v.setCurrentPage}
                onPageCount={v.handlePageCount}
              />
            )}
          </div>
        )}

        {/* 文本面板 */}
        {v.showTextPanel && v.hasTextLayer && (
          <TextPanel
            currentPage={v.currentPage}
            currentTextItems={v.currentTextItems}
            currentTextTotal={v.currentTextTotal}
            onClose={() => v.setShowTextPanel(false)}
          />
        )}

        {/* OCR 结果面板 */}
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

        {/* 图片面板 */}
        {v.showImagePanel && (
          <ImagePanel
            images={v.extractedImages}
            imageBlobUrls={v.imageBlobUrls}
            isLoading={v.isLoadingImages}
            onClose={() => v.setShowImagePanel(false)}
          />
        )}

        {/* 检测详情面板 */}
        {v.isDetectMode && v.selectedDetection !== null && v.currentDetections[v.selectedDetection] && (
          <DetectDetailPanel
            detection={v.currentDetections[v.selectedDetection]}
            index={v.selectedDetection}
            onSave={v.handleSaveMolecule}
            onClose={() => v.setSelectedDetection(null)}
          />
        )}
      </div>
    </div>
  )
}
