import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

/**
 * @deprecated Analytics capabilities have been merged into MoleculeLibrary.
 */
export default function MoleculeAnalytics() {
  const navigate = useNavigate()
  useEffect(() => { void navigate('/molecules', { replace: true }) }, [navigate])
  return null
}
