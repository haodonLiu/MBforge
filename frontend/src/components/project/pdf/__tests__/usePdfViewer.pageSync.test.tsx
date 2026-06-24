import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { usePdfViewer } from '../usePdfViewer'
import type { DocumentEntry } from '../../../../types'

const mockConvertFileSrc = vi.fn()
const mockDetectPageMolecules = vi.fn()
const mockGetCachedDetections = vi.fn()
const mockClearDocumentDetections = vi.fn()
const mockExtractPdfImages = vi.fn()
const mockGetDocumentOcrLayout = vi.fn()
const mockShowToast = vi.fn()

vi.mock('@tauri-apps/api/core', () => ({
  convertFileSrc: (...args: unknown[]) => mockConvertFileSrc(...args),
}))

vi.mock('../../../../services/pdfService', () => ({
  detectPageMolecules: (...args: unknown[]) => mockDetectPageMolecules(...args),
  getCachedDetections: (...args: unknown[]) => mockGetCachedDetections(...args),
  clearDocumentDetections: (...args: unknown[]) => mockClearDocumentDetections(...args),
  extractPdfImages: (...args: unknown[]) => mockExtractPdfImages(...args),
}))

vi.mock('../../../../api/tauri/pdf', () => ({
  getDocumentOcrLayout: (...args: unknown[]) => mockGetDocumentOcrLayout(...args),
}))

vi.mock('../../../../hooks/useToast', () => ({
  showToast: (...args: unknown[]) => mockShowToast(...args),
}))

function makeDoc(): DocumentEntry {
  return {
    doc_id: 'doc-1',
    path: 'papers/test.pdf',
    source_path: 'papers/test.pdf',
    doc_type: 'pdf',
    title: 'Test',
    indexed: false,
  }
}

describe('usePdfViewer page synchronization', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockConvertFileSrc.mockReturnValue('mock://pdf')
    mockGetCachedDetections.mockResolvedValue({ success: true, data: { results: [], count: 0, source: 'cache_miss' } })
    mockDetectPageMolecules.mockResolvedValue({ success: true, data: { results: [], count: 0, source: 'sidecar' } })
    mockExtractPdfImages.mockResolvedValue({ success: true, data: [] })
    mockGetDocumentOcrLayout.mockResolvedValue({ blocks: [] })
    mockClearDocumentDetections.mockResolvedValue({ success: true })
  })

  it('ignores page rendered callback for a stale page', () => {
    const { result } = renderHook(() => usePdfViewer(makeDoc(), '/project', 'detect'))

    act(() => {
      result.current.handlePageRendered({
        pageNumber: 2,
        width: 400,
        height: 600,
        originalWidth: 400,
        originalHeight: 600,
        scale: 1,
      })
    })

    expect(result.current.pageInfo).toBeNull()
  })

  it('accepts page rendered callback only for the current page', () => {
    const { result } = renderHook(() => usePdfViewer(makeDoc(), '/project', 'detect'))

    act(() => {
      result.current.handlePageRendered({
        pageNumber: 1,
        width: 400,
        height: 600,
        originalWidth: 400,
        originalHeight: 600,
        scale: 1,
      })
    })

    expect(result.current.pageInfo).not.toBeNull()
    expect(result.current.pageInfo?.pageNumber).toBe(1)
  })

  it('ignores image ready callback for a stale page', () => {
    const { result } = renderHook(() => usePdfViewer(makeDoc(), '/project', 'detect'))

    act(() => {
      result.current.handleImageReady(2, 'data:image/png;base64,page2')
    })

    expect(result.current.currentPageDataUrl).toBeNull()
  })

  it('accepts image ready callback only for the current page', () => {
    const { result } = renderHook(() => usePdfViewer(makeDoc(), '/project', 'detect'))

    act(() => {
      result.current.handleImageReady(1, 'data:image/png;base64,page1')
    })

    expect(result.current.currentPageDataUrl).toBe('data:image/png;base64,page1')
  })

  it('resets render state when current page changes', async () => {
    const { result } = renderHook(() => usePdfViewer(makeDoc(), '/project', 'detect'))

    act(() => {
      result.current.handlePageRendered({
        pageNumber: 1,
        width: 400,
        height: 600,
        originalWidth: 400,
        originalHeight: 600,
        scale: 1,
      })
      result.current.handleImageReady(1, 'data:image/png;base64,page1')
    })

    expect(result.current.pageInfo).not.toBeNull()
    expect(result.current.currentPageDataUrl).not.toBeNull()

    act(() => {
      result.current.setCurrentPage(2)
    })

    await waitFor(() => {
      expect(result.current.pageInfo).toBeNull()
      expect(result.current.currentPageDataUrl).toBeNull()
      expect(result.current.selectedDetection).toBeNull()
    })
  })

  it('force detection bypasses cache lookup and calls sidecar', async () => {
    mockGetCachedDetections.mockResolvedValue({
      success: true,
      data: { results: [{ esmiles: 'cached' }], count: 1, source: 'cache' },
    })
    mockDetectPageMolecules.mockResolvedValue({
      success: true,
      data: { results: [{ esmiles: 'forced' }], count: 1, source: 'sidecar' },
    })

    // Use read mode to avoid auto-trigger effect.
    const { result } = renderHook(() => usePdfViewer(makeDoc(), '/project', 'read'))

    act(() => {
      result.current.handlePageRendered({
        pageNumber: 1,
        width: 400,
        height: 600,
        originalWidth: 400,
        originalHeight: 600,
        scale: 1,
      })
      result.current.handleImageReady(1, 'data:image/png;base64,page1')
    })

    await act(async () => {
      await result.current.handleDetectPage(true)
    })

    expect(mockGetCachedDetections).not.toHaveBeenCalled()
    expect(mockDetectPageMolecules).toHaveBeenCalledWith(expect.objectContaining({ force: true }))
    expect(result.current.currentDetections.length).toBe(1)
  })

  it('clearing detection cache removes all cached pages', async () => {
    mockDetectPageMolecules.mockResolvedValue({
      success: true,
      data: { results: [{ esmiles: 'C' }], count: 1, source: 'sidecar' },
    })

    // Use read mode to avoid auto-trigger effect repopulating after clear.
    const { result } = renderHook(() => usePdfViewer(makeDoc(), '/project', 'read'))

    act(() => {
      result.current.handlePageRendered({
        pageNumber: 1,
        width: 400,
        height: 600,
        originalWidth: 400,
        originalHeight: 600,
        scale: 1,
      })
      result.current.handleImageReady(1, 'data:image/png;base64,page1')
    })

    await act(async () => {
      await result.current.handleDetectPage()
    })

    expect(result.current.currentDetections.length).toBe(1)

    await act(async () => {
      await result.current.handleClearDetectionCache()
    })

    expect(mockClearDocumentDetections).toHaveBeenCalledWith('/project', 'doc-1')
    expect(result.current.currentDetections.length).toBe(0)
    expect(result.current.selectedDetection).toBeNull()
  })
})
