import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { renderInlineLatex } from '../chatUtils'

describe('renderInlineLatex', () => {
  it('renders inline math', () => {
    render(<span>{renderInlineLatex('Energy $E=mc^2$ value')}</span>)
    expect(screen.getByText(/Energy/)).toBeInTheDocument()
    expect(document.querySelector('.katex')).toBeInTheDocument()
  })

  it('sanitizes injected script tags inside math', () => {
    render(<span>{renderInlineLatex('$\\href{javascript:alert(1)}{x}$')}</span>)
    expect(document.querySelector('script')).not.toBeInTheDocument()
  })
})
