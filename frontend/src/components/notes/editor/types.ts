/**
 * 笔记实体.
 *
 * 由 src-tauri/src/core/notes.rs::Note 序列化而来.
 */
export interface Note {
  id: string
  title: string
  content: string
  tags: string[]
  /** 关联的实体 */
  links: NoteLink[]
  createdAt: string
  updatedAt: string
}

export interface NoteLink {
  type: 'molecule' | 'document' | 'session' | 'note'
  refId: string
  refTitle: string
}
