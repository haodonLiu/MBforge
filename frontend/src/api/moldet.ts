import { fetchJson } from './http'
import type { ExtractionResult } from '../types'

const API_BASE = '/api/v1/moldet'

/** 检测页面中的分子结构（仅返回 bounding boxes） */
export interface DetectPageResponse {
  boxes: { x1: number; y1: number; x2: number; y2: number; conf: number }[]
  count: number
}

export function detectPage(
  imageBase64: string,
): Promise<DetectPageResponse> {
  return fetchJson(`${API_BASE}/detect-page`, {
    method: 'POST',
    body: JSON.stringify({ image_base64: imageBase64 }),
  })
}

/** 提取页面中的分子（检测 + MolScribe 识别） */
export interface ExtractPageResponse {
  results: ExtractionResult[]
  count: number
}

export function extractPage(
  imageBase64: string,
  pageIdx: number,
  pageWPts: number,
  pageHPts: number,
  imageW: number,
  imageH: number,
): Promise<ExtractPageResponse> {
  return fetchJson(`${API_BASE}/extract-page`, {
    method: 'POST',
    body: JSON.stringify({
      image_base64: imageBase64,
      page_idx: pageIdx,
      page_w_pts: pageWPts,
      page_h_pts: pageHPts,
      image_w: imageW,
      image_h: imageH,
    }),
  })
}

/** 对已裁剪区域进行精检测 + 识别 */
export function extractRegion(
  imageBase64: string,
  pageIdx: number,
  bboxPdf: [number, number, number, number],
): Promise<{ result: ExtractionResult }> {
  return fetchJson(`${API_BASE}/extract-region`, {
    method: 'POST',
    body: JSON.stringify({
      image_base64: imageBase64,
      page_idx: pageIdx,
      bbox_pdf: bboxPdf,
    }),
  })
}
