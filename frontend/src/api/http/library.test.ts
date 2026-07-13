import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { cropImageUrl, importDocument } from './library'

describe('cropImageUrl', () => {
  it('joins rel_path and library_root with a single &', () => {
    const url = cropImageUrl('doc1', 'page_0001_mol_0002.png', 'C:\\MBForge\\lib')
    expect(url).toBe(
      '/api/v1/library/documents/doc1/crop?library_root=C%3A%5CMBForge%5Clib&rel_path=page_0001_mol_0002.png'
    )
    expect(url.split('?').length).toBe(2)
  })
})

describe('importDocument', () => {
  const originalFetch = globalThis.fetch
  const fetchMock = vi.fn<typeof globalThis.fetch>()

  function mockFetchResponse(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
      status,
      statusText: status === 200 ? 'OK' : 'Error',
      headers: { 'Content-Type': 'application/json' },
    })
  }

  beforeEach(() => {
    fetchMock.mockReset()
    globalThis.fetch = fetchMock
  })
  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('sends a multipart request via httpFetch and returns the server response', async () => {
    const document = {
      doc_id: 'doc-1',
      title: 'Test',
      file_name: 'test.pdf',
      page_count: 1,
      status: 'ready',
      created_at: '2026-07-13T00:00:00Z',
    }
    fetchMock.mockResolvedValueOnce(mockFetchResponse({ success: true, document }))

    const file = new File(['bytes'], 'test.pdf', { type: 'application/pdf' })
    const result = await importDocument(file, 'My Title')

    expect(result.success).toBe(true)
    expect(result.document).toEqual(document)

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/library/import')
    expect(init?.method).toBe('POST')
    expect(init?.body).toBeInstanceOf(FormData)
  })

  it('does not override the multipart Content-Type header', async () => {
    fetchMock.mockResolvedValueOnce(mockFetchResponse({ success: true }))

    const file = new File(['bytes'], 'test.pdf')
    await importDocument(file)

    const [, init] = fetchMock.mock.calls[0]
    const headers = new Headers(init?.headers)
    expect(headers.get('Content-Type')).toBeNull()
  })

  it('returns an error object when the server responds with non-OK status', async () => {
    fetchMock.mockResolvedValueOnce(mockFetchResponse({ success: false, error: 'upload too large' }, 413))

    const file = new File(['bytes'], 'huge.pdf')
    const result = await importDocument(file)

    expect(result.success).toBe(false)
    expect(result.error).toBeTruthy()
  })
})
