/** Query key factory — centralised, typed, and collocation-friendly.
 *
 *  Usage:
 *    queryClient.invalidateQueries({ queryKey: queryKeys.documents.all })
 *    const { data } = useQuery({ queryKey: queryKeys.documents.list(collectionId), … })
 */

export const queryKeys = {
  library: {
    all: ['library'] as const,
    status: () => [...queryKeys.library.all, 'status'] as const,
  },

  documents: {
    all: ['documents'] as const,
    list: (collectionId?: string) =>
      [...queryKeys.documents.all, { collectionId }] as const,
  },

  ingest: {
    all: ['ingest'] as const,
    queue: (libraryRoot: string) =>
      [...queryKeys.ingest.all, 'queue', libraryRoot] as const,
    stats: (libraryRoot: string) =>
      [...queryKeys.ingest.all, 'stats', libraryRoot] as const,
    logs: (libraryRoot: string, docId: string) =>
      [...queryKeys.ingest.all, 'logs', libraryRoot, docId] as const,
    workerStatus: () =>
      [...queryKeys.ingest.all, 'worker-status'] as const,
  },

  molecules: {
    all: ['molecules'] as const,
    list: (libraryRoot: string) =>
      [...queryKeys.molecules.all, 'list', libraryRoot] as const,
    stats: (libraryRoot: string) =>
      [...queryKeys.molecules.all, 'stats', libraryRoot] as const,
  },

  notes: {
    all: ['notes'] as const,
    list: (libraryRoot: string) =>
      [...queryKeys.notes.all, libraryRoot] as const,
  },

  settings: {
    all: ['settings'] as const,
    get: () => [...queryKeys.settings.all, 'get'] as const,
  },
} as const
