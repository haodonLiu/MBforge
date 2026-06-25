import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { cleanWindowsPath } from '../utils/path'
import type { DocumentEntry } from '../types'

const STORAGE_KEY = 'mbforge_project_root'

// ============================================================================
// ActiveFile — 跨组件文件导航请求（侧边栏文件树 → ProjectView）
// ============================================================================

export interface ActiveFile {
  path: string
  type: 'pdf' | 'markdown'
  mode?: string
}

// ============================================================================
// Tab — 标签栏打开的文件/视图
// ============================================================================

export interface Tab {
  id: string
  type: 'pdf' | 'markdown'
  title: string
  doc: DocumentEntry
  projectRoot: string

}

let _tabIdSeq = 0
function nextTabId(): string {
  _tabIdSeq += 1
  return `tab-${_tabIdSeq}-${Date.now()}`
}

// ============================================================================
// AppState
// ============================================================================

interface AppState {
  /** 当前打开的项目根目录 */
  projectRoot: string
  /** 设置项目根目录（同时持久化到 localStorage） */
  setProjectRoot: (root: string) => void
  /** 通过全局文件树选中的待打开文件 */
  activeFile: ActiveFile | null
  /** 设置待打开文件（ProjectView 消费后应置空） */
  setActiveFile: (file: ActiveFile | null) => void

  // --- 标签栏 ---
  /** 所有打开的标签（不含固定的 Project tab） */
  openTabs: Tab[]
  /** 当前激活的标签 ID。null = Project tab 激活（显示路由内容） */
  activeTabId: string | null
  /** 打开一个文件标签。如果已存在则激活它 */
  openTab: (tab: Omit<Tab, 'id'>) => void
  /** 关闭一个标签。如果关闭的是激活标签，自动激活相邻标签 */
  closeTab: (tabId: string) => void
  /** 激活指定标签。传 null 切回 Project tab */
  setActiveTabId: (tabId: string | null) => void
}

const AppContext = createContext<AppState | null>(null)

// ============================================================================
// AppProvider
// ============================================================================

export function AppProvider({ children }: { children: ReactNode }) {
  const [projectRoot, setProjectRootState] = useState(() => {
    const raw = localStorage.getItem(STORAGE_KEY) || ''
    return cleanWindowsPath(raw)
  })

  const [activeFile, setActiveFile] = useState<ActiveFile | null>(null)
  const [openTabs, setOpenTabs] = useState<Tab[]>([])
  const [activeTabId, setActiveTabId] = useState<string | null>(null)

  const setProjectRoot = useCallback((root: string) => {
    const cleaned = cleanWindowsPath(root)
    try {
      localStorage.setItem(STORAGE_KEY, cleaned)
    } catch (e) {
      console.warn('[AppContext] localStorage quota exceeded:', e)
    }
    setProjectRootState(cleaned)
    // 切换项目时清空所有标签
    setOpenTabs([])
    setActiveTabId(null)
  }, [])

  const openTab = useCallback((tab: Omit<Tab, 'id'>) => {
    // 先读取当前状态，避免闭包捕获旧值
    const tabs = openTabs
    const existing = tabs.find(
      t => t.type === tab.type && t.doc.doc_id === tab.doc.doc_id
    )
    const newId = nextTabId()

    if (existing) {
      setActiveTabId(existing.id)
    } else {
      const newTab: Tab = { ...tab, id: newId }
      setOpenTabs([...tabs, newTab])
      setActiveTabId(newId)
    }
  }, [openTabs])

  const closeTab = useCallback((tabId: string) => {
    setOpenTabs(prev => {
      const idx = prev.findIndex(t => t.id === tabId)
      if (idx === -1) return prev
      const next = prev.filter(t => t.id !== tabId)

      // 用函数式更新读取最新 activeTabId
      setActiveTabId(current => {
        if (current !== tabId) return current
        if (next.length === 0) return null
        // 激活右侧邻居，或左侧
        const newActive = next[Math.min(idx, next.length - 1)]
        return newActive.id
      })

      return next
    })
  }, [])

  return (
    <AppContext.Provider value={{
      projectRoot, setProjectRoot, activeFile, setActiveFile,
      openTabs, activeTabId, openTab, closeTab, setActiveTabId,
    }}>
      {children}
    </AppContext.Provider>
  )
}

/** 获取 App 全局状态。必须在 AppProvider 内部使用。 */
export function useAppContext(): AppState {
  const ctx = useContext(AppContext)
  if (!ctx) {
    throw new Error('useAppContext must be used within <AppProvider>')
  }
  return ctx
}
