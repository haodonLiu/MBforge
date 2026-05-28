import { invoke } from '@tauri-apps/api/core'

/** True when running inside a Tauri webview (desktop app). */
export function isTauriAvailable(): boolean {
  return typeof window !== 'undefined' && '__TAURI__' in window
}

// ---- pdf-inspector ----

export interface PdfClassification {
  pdf_type: string
  confidence: number
  page_count: number
  pages_needing_ocr: number[]
  text_density_avg: number
  has_complex_layout: boolean
  has_encoding_issues: boolean
  title: string | null
}

export interface PdfExtraction {
  markdown: string
  page_count: number
  pages_needing_ocr: number[]
  confidence: number
  has_complex_layout: boolean
  has_encoding_issues: boolean
}

export async function classifyPdf(path: string): Promise<PdfClassification> {
  return invoke<PdfClassification>('classify_pdf', { path })
}

export async function extractText(path: string): Promise<PdfExtraction> {
  return invoke<PdfExtraction>('extract_text', { path })
}
