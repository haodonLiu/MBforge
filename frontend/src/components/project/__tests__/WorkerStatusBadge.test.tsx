import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WorkerStatusBadge } from '../WorkerStatusBadge'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}))

describe('WorkerStatusBadge', () => {
  it('renders online status', () => {
    render(<WorkerStatusBadge status="online" />)
    expect(screen.getByText('queue.workerOnline')).toBeInTheDocument()
  })

  it('renders offline status', () => {
    render(<WorkerStatusBadge status="offline" />)
    expect(screen.getByText('queue.workerOffline')).toBeInTheDocument()
  })

  it('renders unknown status', () => {
    render(<WorkerStatusBadge status="unknown" />)
    expect(screen.getByText('queue.workerUnknown')).toBeInTheDocument()
  })

  it('has correct CSS class for each status', () => {
    const { container } = render(<WorkerStatusBadge status="online" />)
    expect(container.firstChild).toHaveClass('is-online')

    const { container: c2 } = render(<WorkerStatusBadge status="offline" />)
    expect(c2.firstChild).toHaveClass('is-offline')
  })
})
