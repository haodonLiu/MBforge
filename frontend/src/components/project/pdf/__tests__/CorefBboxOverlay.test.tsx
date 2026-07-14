import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { CorefBboxOverlay, type MolClickInfo } from '../CorefBboxOverlay'
import type { CorefPrediction, FigureLabel } from '@/api/http/result_pane'

vi.mock('@/utils/pdf', () => ({
  pdfToCss: () => ({ x: 10, y: 10, w: 20, h: 20 }),
}))

describe('CorefBboxOverlay', () => {
  const figureBoxes = new Map<string, [number, number, number, number]>([
    ['fig.png', [0, 0, 100, 100]],
  ])

  const labels: FigureLabel[] = [
    { id: 1, doc_id: 'd1', page: 1, label_bbox: [0, 0, 0.1, 0.1], label_text: 'A', ocr_conf: 0.9, image_path: 'fig.png' },
    { id: 2, doc_id: 'd1', page: 1, label_bbox: [0.2, 0, 0.3, 0.1], label_text: 'B', ocr_conf: 0.9, image_path: 'fig.png' },
  ]

  it('pairs labels by prediction relationship, not SMILES equality', () => {
    // Two predictions share the same molecule bbox but have different SMILES strings.
    const predictions: CorefPrediction[] = [
      { id: 101, doc_id: 'd1', page: 1, mol_smiles: 'C1CCCCC1', mol_bbox: [0.4, 0.4, 0.6, 0.6], mol_conf: 0.9, label_id: 1, label_text: 'A', label_bbox: [0, 0, 0.1, 0.1], confidence: 0.9, source: 'geometric', is_confirmed: false, image_path: 'fig.png' },
      { id: 102, doc_id: 'd1', page: 1, mol_smiles: 'c1ccccc1', mol_bbox: [0.4, 0.4, 0.6, 0.6], mol_conf: 0.9, label_id: 2, label_text: 'B', label_bbox: [0.2, 0, 0.3, 0.1], confidence: 0.9, source: 'geometric', is_confirmed: false, image_path: 'fig.png' },
    ]

    let captured: MolClickInfo | null = null
    render(
      <CorefBboxOverlay
        labels={labels}
        predictions={predictions}
        threshold={0}
        containerWidth={200}
        containerHeight={200}
        originalHeight={100}
        scale={1}
        figureBoxes={figureBoxes}
        onMolClick={(info) => { captured = info }}
      />,
    )

    const rect = document.querySelector('[data-testid="mol-rect-101"]')
    expect(rect).not.toBeNull()
    rect!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(captured).not.toBeNull()
    // Both labels should be considered paired to the same molecule.
    expect(captured!.pairedLabels.map(l => l.id).sort()).toEqual([1, 2])
  })

  it('does not pair labels that only share SMILES but have different bboxes', () => {
    const predictions: CorefPrediction[] = [
      { id: 201, doc_id: 'd1', page: 1, mol_smiles: 'CCO', mol_bbox: [0.1, 0.1, 0.2, 0.2], mol_conf: 0.9, label_id: 1, label_text: 'A', label_bbox: [0, 0, 0.1, 0.1], confidence: 0.9, source: 'geometric', is_confirmed: false, image_path: 'fig.png' },
      { id: 202, doc_id: 'd1', page: 1, mol_smiles: 'CCO', mol_bbox: [0.3, 0.3, 0.4, 0.4], mol_conf: 0.9, label_id: 2, label_text: 'B', label_bbox: [0.2, 0, 0.3, 0.1], confidence: 0.9, source: 'geometric', is_confirmed: false, image_path: 'fig.png' },
    ]

    let captured: MolClickInfo | null = null
    render(
      <CorefBboxOverlay
        labels={labels}
        predictions={predictions}
        threshold={0}
        containerWidth={200}
        containerHeight={200}
        originalHeight={100}
        scale={1}
        figureBoxes={figureBoxes}
        onMolClick={(info) => { captured = info }}
      />,
    )

    const rect = document.querySelector('[data-testid="mol-rect-201"]')
    expect(rect).not.toBeNull()
    rect!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(captured!.pairedLabels.map(l => l.id)).toEqual([1])
  })
})
