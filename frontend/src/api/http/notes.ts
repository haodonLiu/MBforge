/** Notes API — project-level note storage via HTTP. */

import { httpPost, invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'

export interface NoteLink {
  type: 'molecule' | 'document' | 'session' | 'note'
  refId: string
  refTitle: string
}

export interface Note {
  id: string
  title: string
  content: string
  tags: string[]
  links: NoteLink[]
  createdAt: string
  updatedAt: string
}

export async function notesList(projectRoot: string): Promise<Note[]> {
  return invokeWithError(
    () => httpPost<Note[]>('/api/v1/notes/list', { projectRoot }),
    ErrorCode.ApiError,
  )
}

export async function notesGet(projectRoot: string, id: string): Promise<Note | null> {
  return invokeWithError(
    () => httpPost<Note | null>('/api/v1/notes/get', { projectRoot, id }),
    ErrorCode.ApiError,
  )
}

export async function notesSave(projectRoot: string, note: Note): Promise<Note> {
  return invokeWithError(
    () => httpPost<Note>('/api/v1/notes/save', { projectRoot, note }),
    ErrorCode.ApiError,
  )
}

export async function notesDelete(projectRoot: string, id: string): Promise<boolean> {
  return invokeWithError(
    () => httpPost<boolean>('/api/v1/notes/delete', { projectRoot, id }),
    ErrorCode.ApiError,
  )
}

/** 返回引用了目标笔记的其他笔记列表（反向链接）. */
export async function notesBacklinks(
  projectRoot: string,
  targetId: string,
): Promise<Note[]> {
  return invokeWithError(
    () => httpPost<Note[]>('/api/v1/notes/backlinks', { projectRoot, targetId }),
    ErrorCode.ApiError,
  )
}
