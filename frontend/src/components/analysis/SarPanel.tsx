import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

export default function SarPanel() {
  const navigate = useNavigate()
  useEffect(() => {
    navigate('/molecules', { replace: true })
  }, [navigate])
  return null
}
