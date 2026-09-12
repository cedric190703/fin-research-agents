import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ResearchForm } from './ResearchForm'

describe('ResearchForm', () => {
  it('submits ticker, trimmed question and depth', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<ResearchForm tickers={['AAPL', 'MSFT']} onSubmit={onSubmit} />)
    await userEvent.selectOptions(screen.getByLabelText('Ticker'), 'MSFT')
    const q = screen.getByLabelText('Question')
    await userEvent.clear(q)
    await userEvent.type(q, '  What changed in risk factors?  ')
    await userEvent.selectOptions(screen.getByLabelText('Depth'), 'deep')
    await userEvent.click(screen.getByRole('button', { name: 'Run research' }))
    expect(onSubmit).toHaveBeenCalledWith('MSFT', 'What changed in risk factors?', 'deep')
  })

  it('falls back to the default question when empty', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<ResearchForm tickers={['AAPL']} onSubmit={onSubmit} />)
    await userEvent.clear(screen.getByLabelText('Question'))
    await userEvent.click(screen.getByRole('button', { name: 'Run research' }))
    expect(onSubmit).toHaveBeenCalledWith('AAPL', 'Full research memo', 'standard')
  })

  it('shows API errors inline and disables submit without tickers', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error('LLM runtime not configured'))
    render(<ResearchForm tickers={['AAPL']} onSubmit={onSubmit} />)
    await userEvent.click(screen.getByRole('button', { name: 'Run research' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('LLM runtime not configured')

    render(<ResearchForm tickers={[]} onSubmit={onSubmit} />)
    expect(screen.getAllByRole('button', { name: 'Run research' })[1]).toBeDisabled()
    expect(screen.getByText('Ingest a ticker first.')).toBeInTheDocument()
  })
})
