import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatPill } from '../StatPill'

describe('StatPill', () => {
  it('renders label and value', () => {
    render(<StatPill label="Total" value={42} tone="neutral" />)
    expect(screen.getByText('Total')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('renders icon when provided', () => {
    render(<StatPill label="Active" value={5} tone="info" icon={<span data-testid="icon">●</span>} />)
    expect(screen.getByTestId('icon')).toBeInTheDocument()
  })

  it('applies pulse class for pulsing pills', () => {
    const { container } = render(<StatPill label="Processing" value={3} tone="info" pulse />)
    const valueEl = container.querySelector('.queue-stat-pill-value')
    expect(valueEl).toHaveClass('is-pulse')
  })

  it('applies tone class', () => {
    const { container } = render(<StatPill label="Err" value={1} tone="danger" />)
    expect(container.firstChild).toHaveClass('is-danger')
  })
})
