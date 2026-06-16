import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

export default function SARAnalysis() {
  const navigate = useNavigate()
  useEffect(() => {
    navigate('/molecules', { replace: true })
  }, [navigate])
  return null
}
