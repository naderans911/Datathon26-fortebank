import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { Results } from './Results'
import { job } from '../test/fixtures'
describe('evidence review', () => {
  it('selects by event ID even when timestamps match, seeks and opens evidence', () => {
    render(<Results job={job} />)
    const video = screen.getByLabelText('Video preview') as HTMLVideoElement
    fireEvent.click(
      screen.getByRole('button', { name: 'Review event 2: Second simultaneous event at 00:04' }),
    )
    expect(video.currentTime).toBe(4)
    expect(screen.getByRole('heading', { name: 'Second simultaneous event' })).toBeInTheDocument()
    expect(
      screen.getByText('A blue circle touches the line.', { selector: '.inspector-copy p' }),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Enlarge evidence frame 00:04' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('qualifies a negative verdict', () => {
    render(
      <Results job={{ ...job, result: { ...job.result!, verdict: 'no_violation', events: [] } }} />,
    )
    expect(screen.getByRole('heading', { name: 'No violation detected' })).toBeInTheDocument()
    expect(screen.getByText(/not proof of complete compliance/)).toBeInTheDocument()
    expect(screen.getAllByText('No mapped events to review').length).toBeGreaterThan(0)
  })
  it('presents an unclassified candidate without inventing a rule source', () => {
    render(
      <Results
        job={{
          ...job,
          result: { ...job.result!, events: [{ ...job.result!.events[0], rule: null }] },
        }}
      />,
    )
    expect(screen.getByText(/No verified rule mapping; human review required/)).toBeInTheDocument()
    expect(screen.queryByText('Synthetic demonstration rule')).not.toBeInTheDocument()
  })
})
