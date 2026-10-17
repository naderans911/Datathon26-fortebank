import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import { StatusProvider } from '../app/StatusContext'
import { UploadPage } from './UploadPage'
import { status } from '../test/fixtures'
function setup(ready: boolean) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({ ...status, ready }), { status: 200 })),
    ),
  )
  render(
    <MemoryRouter>
      <StatusProvider>
        <UploadPage />
      </StatusProvider>
    </MemoryRouter>,
  )
}
describe('upload readiness', () => {
  it('does not enable real analysis when the backend is not ready', async () => {
    setup(false)
    fireEvent.change(screen.getByLabelText('Select a video to analyze'), {
      target: { files: [new File(['synthetic'], 'sample.mov')] },
    })
    await waitFor(() => expect(screen.getByText('Selected video')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Analyze video' })).toBeDisabled()
  })
  it('accepts valid MOV and enables submission only after backend readiness', async () => {
    setup(true)
    expect(screen.getByRole('button', { name: 'Analyze video' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Select a video to analyze'), {
      target: { files: [new File(['synthetic'], 'sample.mov')] },
    })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Analyze video' })).toBeEnabled())
    expect(screen.getByText('sample.mov')).toBeInTheDocument()
  })
  it('rejects invalid extension visibly', () => {
    setup(true)
    fireEvent.change(screen.getByLabelText('Select a video to analyze'), {
      target: { files: [new File(['x'], 'secret.txt')] },
    })
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a .mov')
    expect(screen.getByRole('button', { name: 'Analyze video' })).toBeDisabled()
  })
})
