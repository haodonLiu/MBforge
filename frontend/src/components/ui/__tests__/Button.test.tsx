import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import Button from '../Button'

describe('Button', () => {
  it('renders children text', () => {
    render(<Button>Click me</Button>)
    expect(screen.getByText('Click me')).toBeInTheDocument()
  })

  it('calls onClick when clicked', () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Click</Button>)
    fireEvent.click(screen.getByText('Click'))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('is disabled when disabled prop is true', () => {
    const onClick = vi.fn()
    render(<Button disabled onClick={onClick}>Click</Button>)
    const btn = screen.getByText('Click').closest('button')
    expect(btn).toBeDisabled()
    fireEvent.click(btn!)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('shows loading spinner and prevents click', () => {
    const onClick = vi.fn()
    render(<Button loading onClick={onClick}>Load</Button>)
    const btn = screen.getByText('Load').closest('button')
    expect(btn).toBeDisabled()
    const spinner = btn?.querySelector('span')
    expect(spinner).toBeInTheDocument()
    fireEvent.click(btn!)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('renders icon alongside children', () => {
    render(<Button icon={<span data-testid="icon">🔍</span>}>Search</Button>)
    expect(screen.getByTestId('icon')).toBeInTheDocument()
    expect(screen.getByText('Search')).toBeInTheDocument()
  })

  it('applies all variant styles', () => {
    const variants = ['primary', 'secondary', 'ghost', 'danger', 'dashed'] as const
    for (const variant of variants) {
      const { unmount } = render(<Button variant={variant}>{variant}</Button>)
      expect(screen.getByText(variant)).toBeInTheDocument()
      unmount()
    }
  })

  it('applies all size styles', () => {
    const sizes = ['sm', 'md', 'lg'] as const
    for (const size of sizes) {
      const { unmount } = render(<Button size={size}>{size}</Button>)
      expect(screen.getByText(size)).toBeInTheDocument()
      unmount()
    }
  })

  it('renders with type attribute', () => {
    render(<Button type="submit">Submit</Button>)
    expect(screen.getByText('Submit').closest('button')).toHaveAttribute('type', 'submit')
  })

  it('sets title attribute', () => {
    render(<Button title="tooltip">Hover</Button>)
    expect(screen.getByText('Hover').closest('button')).toHaveAttribute('title', 'tooltip')
  })

  it('forwards className', () => {
    const { container } = render(<Button className="custom-btn">Styled</Button>)
    expect(container.firstChild).toHaveClass('custom-btn')
  })

  it('merges custom style', () => {
    const { container } = render(<Button style={{ background: 'red' }}>Red</Button>)
    expect(container.firstChild).toHaveStyle({ background: 'red' })
  })

  it('defaults to type button', () => {
    render(<Button>Default</Button>)
    expect(screen.getByText('Default').closest('button')).toHaveAttribute('type', 'button')
  })
})
