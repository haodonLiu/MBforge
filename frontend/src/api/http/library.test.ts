import { describe, it, expect } from 'vitest'
import { cropImageUrl } from './library'

describe('cropImageUrl', () => {
  it('joins rel_path and library_root with a single &', () => {
    const url = cropImageUrl('doc1', 'page_0001_mol_0002.png', 'C:\\MBForge\\lib')
    expect(url).toBe(
      '/api/v1/library/documents/doc1/crop?library_root=C%3A%5CMBForge%5Clib&rel_path=page_0001_mol_0002.png'
    )
    expect(url.split('?').length).toBe(2)
  })
})
