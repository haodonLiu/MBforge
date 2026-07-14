import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../_utils', () => ({
  httpPost: vi.fn(),
}))

import { httpPost } from '../_utils'
import {
  getCorefPredictions,
  getFigureLabels,
  type CorefPrediction,
  type FigureLabel,
} from '../result_pane'

const mockHttpPost = vi.mocked(httpPost)

describe('coref result pane API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('unwraps figure labels from the backend response envelope', async () => {
    const labels: FigureLabel[] = [{
      id: 1,
      doc_id: 'doc-1',
      page: 1,
      label_bbox: [0.1, 0.2, 0.3, 0.4],
      label_text: '1a',
      ocr_conf: 0.98,
      image_path: null,
    }]
    mockHttpPost.mockResolvedValue({ labels })

    await expect(getFigureLabels('C:/library', 'doc-1', 1)).resolves.toEqual(labels)
    expect(httpPost).toHaveBeenCalledWith('/api/v1/coref/figure-labels', {
      libraryRoot: 'C:/library',
      docId: 'doc-1',
      page: 1,
    })
  })

  it('unwraps coref predictions from the backend response envelope', async () => {
    const predictions: CorefPrediction[] = [{
      id: 2,
      doc_id: 'doc-1',
      page: 1,
      mol_smiles: 'CCO',
      mol_bbox: [0.1, 0.2, 0.3, 0.4],
      mol_conf: 0.95,
      label_id: 1,
      label_text: '1a',
      label_bbox: [0.5, 0.6, 0.7, 0.8],
      confidence: 0.91,
      source: 'geometric',
      is_confirmed: false,
      image_path: null,
    }]
    mockHttpPost.mockResolvedValue({ predictions })

    await expect(getCorefPredictions('C:/library', 'doc-1', 1)).resolves.toEqual(predictions)
    expect(httpPost).toHaveBeenCalledWith('/api/v1/coref/predictions', {
      libraryRoot: 'C:/library',
      docId: 'doc-1',
      page: 1,
    })
  })

  it('returns empty arrays when a backend response omits the expected collection', async () => {
    mockHttpPost.mockResolvedValue({})
    await expect(getFigureLabels('C:/library', 'doc-1', 1)).resolves.toEqual([])

    mockHttpPost.mockResolvedValue({ labels: [] })
    await expect(getCorefPredictions('C:/library', 'doc-1', 1)).resolves.toEqual([])
  })
})
