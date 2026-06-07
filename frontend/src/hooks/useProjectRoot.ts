import { useState, useCallback } from 'react'
import { cleanWindowsPath } from '../utils/path'

const STORAGE_KEY = 'mbforge_project_root'

export function getProjectRoot(): string {
  const raw = localStorage.getItem(STORAGE_KEY) || ''
  return cleanWindowsPath(raw)
}

export function setProjectRoot(root: string): void {
  localStorage.setItem(STORAGE_KEY, cleanWindowsPath(root))
}

export function useProjectRoot() {
  const [projectRoot, setProjectRootState] = useState(getProjectRoot)

  const updateProjectRoot = useCallback((root: string) => {
    const cleaned = cleanWindowsPath(root)
    setProjectRoot(cleaned)
    setProjectRootState(cleaned)
  }, [])

  return { projectRoot, setProjectRoot: updateProjectRoot }
}
