import { useState, useCallback } from 'react'

const STORAGE_KEY = 'mbforge_project_root'

export function getProjectRoot(): string {
  return localStorage.getItem(STORAGE_KEY) || ''
}

export function setProjectRoot(root: string): void {
  localStorage.setItem(STORAGE_KEY, root)
}

export function useProjectRoot() {
  const [projectRoot, setProjectRootState] = useState(getProjectRoot)

  const updateProjectRoot = useCallback((root: string) => {
    setProjectRoot(root)
    setProjectRootState(root)
  }, [])

  return { projectRoot, setProjectRoot: updateProjectRoot }
}
