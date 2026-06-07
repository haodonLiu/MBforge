import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { cleanWindowsPath } from '../utils/path'

const STORAGE_KEY = 'mbforge_project_root'

export interface ActiveFile {
  path: string
  type: 'pdf' | 'markdown'
  mode?: string
}

interface AppState {
  /** 当前打开的项目根目录 */
  projectRoot: string
  /** 设置项目根目录（同时持久化到 localStorage） */
  setProjectRoot: (root: string) => void
  /** 通过全局文件树选中的待打开文件 */
  activeFile: ActiveFile | null
  /** 设置待打开文件（ProjectView 消费后应置空） */
  setActiveFile: (file: ActiveFile | null) => void
}

const AppContext = createContext<AppState | null>(null)

/**
 * App 全局状态 Provider。
 *
 * 当前管理：
 * - projectRoot：项目根目录，持久化到 localStorage
 * - activeFile：侧边栏文件树点击后待打开的文件，用于跨组件路由到对应阅读器
 *
 * 未来可扩展：settings、agent session 等全局状态。
 */
export function AppProvider({ children }: { children: ReactNode }) {
  const [projectRoot, setProjectRootState] = useState(() => {
    const raw = localStorage.getItem(STORAGE_KEY) || ''
    return cleanWindowsPath(raw)
  })

  const [activeFile, setActiveFile] = useState<ActiveFile | null>(null)

  const setProjectRoot = useCallback((root: string) => {
    const cleaned = cleanWindowsPath(root)
    localStorage.setItem(STORAGE_KEY, cleaned)
    setProjectRootState(cleaned)
  }, [])

  return (
    <AppContext.Provider value={{ projectRoot, setProjectRoot, activeFile, setActiveFile }}>
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
