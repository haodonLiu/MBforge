/** Notes API — project-level note storage via Rust JSON persistence. */

import { invoke } from '@tauri-apps/api/core'
import { invokeWithError } from './_utils'
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
    () => invoke<Note[]>('notes_list', { project_root: projectRoot }),
    ErrorCode.ApiError,
  )
}

export async function notesGet(projectRoot: string, id: string): Promise<Note | null> {
  return invokeWithError(
    () => invoke<Note | null>('notes_get', { project_root: projectRoot, id }),
    ErrorCode.ApiError,
  )
}

export async function notesSave(projectRoot: string, note: Note): Promise<Note> {
  return invokeWithError(
    () => invoke<Note>('notes_save', { project_root: projectRoot, note }),
    ErrorCode.ApiError,
  )
}

export async function notesDelete(projectRoot: string, id: string): Promise<boolean> {
  return invokeWithError(
    () => invoke<boolean>('notes_delete', { project_root: projectRoot, id }),
    ErrorCode.ApiError,
  )
}

/** 返回引用了目标笔记的其他笔记列表（反向链接）. */
export async function notesBacklinks(
  projectRoot: string,
  targetId: string,
): Promise<Note[]> {
  return invokeWithError(
    () => invoke<Note[]>('notes_backlinks', { project_root: projectRoot, target_id: targetId }),
    ErrorCode.ApiError,
  )
}