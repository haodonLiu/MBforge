import { getSettings, saveSettings } from '@/api/http/settings'
import { cleanWindowsPath } from '../../utils/path'

export interface RecentProject {
  root: string
  name: string
}

const MAX_RECENT = 20

function dedupeAndCap(list: RecentProject[]): RecentProject[] {
  const seen = new Set<string>()
  const out: RecentProject[] = []
  for (const p of list) {
    if (!p.root || seen.has(p.root)) continue
    seen.add(p.root)
    out.push(p)
    if (out.length >= MAX_RECENT) break
  }
  return out
}

/** 从后端 /api/v1/settings.recent_projects 拉取;失败回退到空列表. */
export async function loadRecent(): Promise<RecentProject[]> {
  try {
    const resp = await getSettings()
    if (!resp.success || !resp.settings) return []
    const list = resp.settings.recent_projects ?? []
    return list.map((p) => ({ root: cleanWindowsPath(p.root), name: p.name }))
  } catch {
    return []
  }
}

async function writeRecent(list: RecentProject[]): Promise<RecentProject[]> {
  const next = dedupeAndCap(list)
  await saveSettings({ recent_projects: next })
  return next
}

/** 追加新项目到最近列表(去重,新者在前),持久化到后端. */
export async function persistRecent(root: string, name: string): Promise<RecentProject[]> {
  const cleaned = cleanWindowsPath(root)
  const current = await loadRecent()
  const filtered = current.filter((p) => p.root !== cleaned)
  const fallbackName = cleaned.split(/[/\\]/).pop() || cleaned
  return writeRecent([{ root: cleaned, name: name || fallbackName }, ...filtered])
}

/** 从最近列表移除并持久化. */
export async function removeRecentFromStorage(root: string): Promise<RecentProject[]> {
  const current = await loadRecent()
  return writeRecent(current.filter((p) => p.root !== root))
}

export function sanitizePath(p: string): string {
  return p.replace(/^["']+|["']+$/g, '').trim()
}