import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import Card from '../Card'

describe('Card', () => {
  it('renders children', () => {
    render(<Card><span data-testid="child">content</span></Card>)
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })

  it('renders plain div when not hoverable and no onClick', () => {
    const { container } = render(<Card>plain</Card>)
    const el = container.firstChild
    expect(el?.nodeName).toBe('DIV')
    expect(el).not.toHaveClass('motion-div')
  })

  it('renders motion.div when hoverable', () => {
    const { container } = render(<Card hoverable>hover</Card>)
    expect(screen.getByText('hover')).toBeInTheDocument()
    expect(container.firstChild).toBeTruthy()
  })

  it('renders motion.div when onClick provided', () => {
    const { container } = render(<Card onClick={() => {}}>clickable</Card>)
    expect(screen.getByText('clickable')).toBeInTheDocument()
    expect(container.firstChild).toBeTruthy()
  })

  it('calls onClick when clicked', () => {
    const onClick = vi.fn()
    render(<Card onClick={onClick}>click</Card>)
    fireEvent.click(screen.getByText('click'))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('applies custom padding', () => {
    const { container } = render(<Card padding="40px">padded</Card>)
    expect(container.firstChild).toHaveStyle({ padding: '40px' })
  })

  it('applies numeric padding', () => {
    const { container } = render(<Card padding={24}>num</Card>)
    expect(container.firstChild).toHaveStyle({ padding: '24px' })
  })

  it('forwards className', () => {
    const { container } = render(<Card className="custom-card">classy</Card>)
    expect(container.firstChild).toHaveClass('custom-card')
  })

  it('merges custom style', () => {
    const { container } = render(<Card style={{ margin: '10px' }}>styled</Card>)
    expect(container.firstChild).toHaveStyle({ margin: '10px' })
  })
})
