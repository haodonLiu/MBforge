import { describe, it, expect } from 'vitest'
import { queryKeys } from '../keys'

describe('queryKeys', () => {
  it('library.status produces stable keys', () => {
    const a = queryKeys.library.status()
    const b = queryKeys.library.status()
    expect(a).toEqual(b)
    expect(a).toEqual(['library', 'status'])
  })

  it('documents.list includes collectionId', () => {
    const key = queryKeys.documents.list('col-1')
    expect(key).toEqual(['documents', { collectionId: 'col-1' }])
  })

  it('ingest.queue includes libraryRoot', () => {
    const key = queryKeys.ingest.queue('/tmp/lib')
    expect(key).toEqual(['ingest', 'queue', '/tmp/lib'])
  })

  it('molecules.list is scoped by root', () => {
    const key = queryKeys.molecules.list('/lib')
    expect(key).toEqual(['molecules', 'list', '/lib'])
  })

  it('notes.list scoped by root', () => {
    const key = queryKeys.notes.list('/r')
    expect(key).toEqual(['notes', '/r'])
  })
})
