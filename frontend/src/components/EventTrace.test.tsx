import { render, screen } from '@testing-library/react'
import { EventTrace } from './EventTrace'
import { EVENTS } from '../test/fixtures'

describe('EventTrace', () => {
  it('shows a waiting message when empty', () => {
    render(<EventTrace events={[]} />)
    expect(screen.getByText(/Waiting for the first event/)).toBeInTheDocument()
  })

  it('describes each event type in analyst terms', () => {
    render(<EventTrace events={EVENTS} />)
    expect(screen.getByText('AAPL · deep · “q”')).toBeInTheDocument()
    expect(screen.getByText('filings_analyst: risk factors')).toBeInTheDocument()
    expect(screen.getByText('search_filings({"query":"Taiwan"})')).toBeInTheDocument()
    expect(screen.getByText('1 claim(s) not supported')).toBeInTheDocument()
    expect(screen.getByText('RuntimeError: boom')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(EVENTS.length)
  })
})
