import { cleanWindowsPath } from '../../utils/path'

export interface RecentProject {
  name: string
  path: string
}

const RECENT_KEY = 'mbforge_recent_projects'
const MAX_RECENT = 20

export function loadRecent(): RecentProject[] {
  try {
    const raw: RecentProject[] = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]')
    return raw.map(r => ({ ...r, path: cleanWindowsPath(r.path) }))
  } catch {
    return []
  }
}

export function persistRecent(path: string, name: string) {
  const cleaned = cleanWindowsPath(path)
  const list = loadRecent()
  const filtered = list.filter(p => p.path !== cleaned)
  const next = [
    { name: name || cleaned.split(/[/\\]/).pop() || cleaned, path: cleaned },
    ...filtered,
  ].slice(0, MAX_RECENT)
  localStorage.setItem(RECENT_KEY, JSON.stringify(next))
}

export function removeRecentFromStorage(path: string) {
  const list = loadRecent().filter(p => p.path !== path)
  localStorage.setItem(RECENT_KEY, JSON.stringify(list))
  return list
}

export function sanitizePath(p: string): string {
  return p.replace(/^["']+|["']+$/g, '').trim()
}
