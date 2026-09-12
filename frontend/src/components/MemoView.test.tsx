import { render, screen, within } from '@testing-library/react'
import { MemoView } from './MemoView'
import { RESULT } from '../test/fixtures'

describe('MemoView', () => {
  it('renders title, thesis, sections and disclaimer', () => {
    render(<MemoView result={RESULT} />)
    expect(screen.getByRole('heading', { name: RESULT.memo.title })).toBeInTheDocument()
    expect(screen.getByText(RESULT.memo.thesis)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Risks' })).toBeInTheDocument()
    expect(screen.getByText('Research support only. Not investment advice.')).toBeInTheDocument()
  })

  it('flags unverified claims and shows reference chips', () => {
    render(<MemoView result={RESULT} />)
    const flagged = screen.getByText(/Management expects tariffs/).closest('li')!
    expect(flagged).toHaveClass('unverified')
    expect(within(flagged).getByText('Unverified:')).toBeInTheDocument()
    const supported = screen.getByText(/Supplier concentration/).closest('li')!
    expect(supported).not.toHaveClass('unverified')
    expect(within(supported).getByText('F1')).toBeInTheDocument()
    // Long metric ids are truncated but still labelled as metrics
    const metric = screen.getByText(/Gross margin reached/).closest('li')!
    expect(within(metric).getByTitle('Metric')).toHaveTextContent(/^Mcompute_rat…$/)
  })

  it('shows the critic verdict and cost ledger', () => {
    render(<MemoView result={RESULT} />)
    expect(screen.getByRole('status')).toHaveTextContent('Critic: unsupported claims flagged')
    expect(screen.getByText('2 claims checked')).toBeInTheDocument()
    expect(screen.getByText('$0.4321')).toBeInTheDocument()
    expect(screen.getByText('12,000')).toBeInTheDocument()
  })

  it('omits the verdict block for brief runs', () => {
    render(<MemoView result={{ ...RESULT, verdict: null, depth: 'brief' }} />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
