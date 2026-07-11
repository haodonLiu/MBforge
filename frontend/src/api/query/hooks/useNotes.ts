/** React Query hooks for notes CRUD. */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notesList, notesSave, notesDelete } from '../../http/notes'
import { queryKeys } from '../keys'
import type { Note } from '../../http/notes'

/** Fetch all notes for a given library root. */
export function useNotes(libraryRoot: string) {
  return useQuery({
    queryKey: queryKeys.notes.list(libraryRoot),
    queryFn: () => notesList(libraryRoot),
  })
}

/** Create or update a note. */
export function useSaveNote() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: ({
      libraryRoot,
      note,
    }: {
      libraryRoot: string
      note: Note
    }) => notesSave(libraryRoot, note),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({
        queryKey: queryKeys.notes.list(variables.libraryRoot),
      })
    },
  })
}

/** Delete a note. */
export function useDeleteNote() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: ({
      libraryRoot,
      noteId,
    }: {
      libraryRoot: string
      noteId: string
    }) => notesDelete(libraryRoot, noteId),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({
        queryKey: queryKeys.notes.list(variables.libraryRoot),
      })
    },
  })
}
