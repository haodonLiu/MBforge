import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react'
import { cleanWindowsPath } from '../utils/path'
import type { DocumentEntry } from '../types'

const STORAGE_KEY = 'mbforge_library_root'

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
  libraryRoot: string
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
  /** Legacy project root (deprecated) */
  projectRoot: string
  /** Legacy setter (deprecated) */
  setProjectRoot: (root: string) => void
  /** Unified library root directory */
  libraryRoot: string
  /** Set library root (persists to localStorage) */
  setLibraryRoot: (root: string) => void
  /** Active collection filter (null = show all) */
  activeCollectionId: string | null
  /** Set active collection filter */
  setActiveCollectionId: (id: string | null) => void
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

  /** Files panel (Library + Groups) collapsed in left rail */
  libraryPanelCollapsed: boolean
  /** Toggle files panel visibility, persisted to localStorage */
  setLibraryPanelCollapsed: (collapsed: boolean) => void
}

const AppContext = createContext<AppState | null>(null)

// ============================================================================
// AppProvider
// ============================================================================

export function AppProvider({ children }: { children: ReactNode }) {
  const [projectRoot, setProjectRootState] = useState(() => {
    const raw = localStorage.getItem('mbforge_project_root') || ''
    return cleanWindowsPath(raw)
  })

  const [libraryRoot, setLibraryRootState] = useState(() => {
    const raw = localStorage.getItem(STORAGE_KEY) || ''
    return cleanWindowsPath(raw)
  })

  const [activeFile, setActiveFile] = useState<ActiveFile | null>(null)
  const [openTabs, setOpenTabs] = useState<Tab[]>([])
  const [activeTabId, setActiveTabId] = useState<string | null>(null)
  const [activeCollectionId, setActiveCollectionId] = useState<string | null>(null)

  const [libraryPanelCollapsed, setLibraryPanelCollapsedState] = useState<boolean>(() => {
    try {
      return localStorage.getItem('mbforge_library_panel_collapsed') === 'true'
    } catch {
      return false
    }
  })

  const setProjectRoot = useCallback((root: string) => {
    const cleaned = cleanWindowsPath(root)
    try {
      localStorage.setItem('mbforge_project_root', cleaned)
    } catch (e) {
      console.warn('[AppContext] localStorage quota exceeded:', e)
    }
    setProjectRootState(cleaned)
    setOpenTabs([])
    setActiveTabId(null)
  }, [])

  const setLibraryRoot = useCallback((root: string) => {
    const cleaned = cleanWindowsPath(root)
    try {
      localStorage.setItem(STORAGE_KEY, cleaned)
    } catch (e) {
      console.warn('[AppContext] localStorage quota exceeded:', e)
    }
    setLibraryRootState(cleaned)
    setOpenTabs([])
    setActiveTabId(null)
  }, [])

  const openTab = useCallback((tab: Omit<Tab, 'id'>) => {
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

      setActiveTabId(current => {
        if (current !== tabId) return current
        if (next.length === 0) return null
        const newActive = next[Math.min(idx, next.length - 1)]
        return newActive.id
      })

      return next
    })
  }, [])

  const setLibraryPanelCollapsed = useCallback((collapsed: boolean) => {
    try {
      localStorage.setItem('mbforge_library_panel_collapsed', String(collapsed))
    } catch (e) {
      console.warn('[AppContext] localStorage quota exceeded:', e)
    }
    setLibraryPanelCollapsedState(collapsed)
  }, [])

  return (
    <AppContext.Provider value={{
      projectRoot, setProjectRoot,
      libraryRoot, setLibraryRoot,
      activeCollectionId, setActiveCollectionId,
      activeFile, setActiveFile,
      openTabs, activeTabId, openTab, closeTab, setActiveTabId,
      libraryPanelCollapsed, setLibraryPanelCollapsed,
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
