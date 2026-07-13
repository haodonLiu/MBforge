/** React Query hooks for document CRUD. */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listDocuments,
  importDocument,
  deleteDocument,
} from '../../http/library'
import type { DocumentInfo } from '../../http/library'
import { queryKeys } from '../keys'

/**
 * List documents, optionally filtered by collection.
 *
 * The document list changes when the user imports / deletes / refreshes,
 * so we keep the default staleTime.
 */
export function useDocuments(collectionId?: string) {
  return useQuery({
    queryKey: queryKeys.documents.list(collectionId),
    queryFn: () => listDocuments(collectionId),
  })
}

/** Upload a PDF and enqueue it for pipeline processing. */
export function useImportDocument() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: ({ file, title }: { file: File; title?: string }) =>
      importDocument(file, title),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.documents.all })
      void qc.invalidateQueries({ queryKey: queryKeys.ingest.all })
    },
  })
}

/** Delete a document and its pipeline tasks. */
export function useDeleteDocument() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: (docId: string) => deleteDocument(docId),
    onMutate: async (docId) => {
      await qc.cancelQueries({ queryKey: queryKeys.documents.all })

      const previous = qc.getQueriesData<{ documents: DocumentInfo[] }>({
        queryKey: queryKeys.documents.all,
      })

      qc.setQueriesData<{ documents: DocumentInfo[] }>(
        { queryKey: queryKeys.documents.all },
        (current) => {
          if (!current) return current
          return {
            ...current,
            documents: current.documents.filter((document) => document.doc_id !== docId),
          }
        },
      )

      return { previous }
    },
    onError: (_error, _docId, context) => {
      context?.previous.forEach(([queryKey, data]) => {
        qc.setQueryData(queryKey, data)
      })
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.documents.all })
    },
  })
}
