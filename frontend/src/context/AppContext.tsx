import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'

const STORAGE_KEY = 'mbforge_project_root'

interface AppState {
  /** 当前打开的项目根目录 */
  projectRoot: string
  /** 设置项目根目录（同时持久化到 localStorage） */
  setProjectRoot: (root: string) => void
}

const AppContext = createContext<AppState | null>(null)

/**
 * App 全局状态 Provider。
 *
 * 当前管理：
 * - projectRoot：项目根目录，持久化到 localStorage
 *
 * 未来可扩展：settings、agent session 等全局状态。
 */
export function AppProvider({ children }: { children: ReactNode }) {
  const [projectRoot, setProjectRootState] = useState(() => {
    return localStorage.getItem(STORAGE_KEY) || ''
  })

  const setProjectRoot = useCallback((root: string) => {
    localStorage.setItem(STORAGE_KEY, root)
    setProjectRootState(root)
  }, [])

  return (
    <AppContext.Provider value={{ projectRoot, setProjectRoot }}>
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
