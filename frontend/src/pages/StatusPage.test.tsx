import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { StatusProvider } from '../app/StatusContext'
import { StatusPage } from './StatusPage'
import { status } from '../test/fixtures'

it('shows model limitations even when the local components are ready', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            ...status,
            ready: true,
            detector_name: 'cv-local',
            notices: ['Binary model quality is unvalidated and scores are uncalibrated.'],
          }),
          { status: 200 },
        ),
    ),
  )
  render(
    <StatusProvider>
      <StatusPage />
    </StatusProvider>,
  )
  expect(await screen.findByRole('heading', { name: 'Local engine ready' })).toBeInTheDocument()
  expect(screen.getByText('Model limitations')).toBeInTheDocument()
  expect(screen.getByText(/quality is unvalidated and scores are uncalibrated/)).toBeInTheDocument()
})
