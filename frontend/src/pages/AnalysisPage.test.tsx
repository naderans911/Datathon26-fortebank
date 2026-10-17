import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import { AnalysisPage, JobView } from './AnalysisPage'
import { job } from '../test/fixtures'
describe('persisted jobs', () => {
  it('recovers an existing job from its URL and stops polling terminal results', async () => {
    const fetcher = vi.fn((url: string) =>
      Promise.resolve(
        new Response(
          JSON.stringify(url.endsWith('/session') ? { csrf_token: 'synthetic-token' } : job),
          { status: 200 },
        ),
      ),
    )
    vi.stubGlobal('fetch', fetcher)
    render(
      <MemoryRouter initialEntries={['/analysis/synthetic-job']}>
        <Routes>
          <Route path="/analysis/:jobId" element={<AnalysisPage />} />
        </Routes>
      </MemoryRouter>,
    )
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Signs of possible violations detected' }),
      ).toBeInTheDocument(),
    )
    expect(fetcher).toHaveBeenCalledWith('/api/ui/jobs/synthetic-job', expect.anything())
    expect(fetcher.mock.calls.filter(([url]) => url.includes('/jobs/'))).toHaveLength(1)
  })
  it('never renders a successful verdict for failed jobs', () => {
    render(
      <MemoryRouter>
        <JobView
          job={{
            ...job,
            status: 'failed',
            result: undefined,
            error: { code: 'deadline_exceeded', message: 'Analysis exceeded its deadline.' },
          }}
        />
      </MemoryRouter>,
    )
    expect(
      screen.getByRole('heading', { name: 'Analysis could not be completed' }),
    ).toBeInTheDocument()
    expect(screen.queryByText('No violation detected')).not.toBeInTheDocument()
  })
})
