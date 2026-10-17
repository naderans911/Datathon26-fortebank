import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ReviewPage } from './ReviewPage'
import { getReviewItem, getReviewItems, saveAnnotation } from '../lib/review'
import type { ReviewDetail } from '../lib/review'

vi.mock('../lib/review', async (original) => ({
  ...(await original<typeof import('../lib/review')>()),
  getReviewItems: vi.fn(),
  getReviewItem: vi.fn(),
  saveAnnotation: vi.fn(),
}))
const fixture: ReviewDetail = {
  source: {
    id: 'synthetic-review',
    filename: 'synthetic.mov',
    has_violation: true,
    timestamp_sec: 4,
    duration_sec: 12,
    review_status: 'draft',
    event_count: 0,
  },
  annotation: { revision: 0, status: 'draft', events: [], notes: '' },
  video_url: '/synthetic.mp4',
}
beforeEach(() => {
  vi.mocked(getReviewItems).mockResolvedValue({ items: [fixture.source], excluded_count: 0 })
  vi.mocked(getReviewItem).mockResolvedValue(structuredClone(fixture))
  vi.mocked(saveAnnotation).mockImplementation(async (_id, annotation) => ({
    annotation: { ...annotation, revision: annotation.revision + 1 },
  }))
})

describe('isolated human annotations', () => {
  it('keeps source points immutable and starts multiple events with empty boundaries and categories', async () => {
    render(<ReviewPage enabled />)
    await screen.findByRole('button', { name: 'Add event' })
    const video = screen.getByLabelText('Matched video preview') as HTMLVideoElement
    Object.defineProperty(video, 'readyState', { configurable: true, value: 4 })
    fireEvent.loadedMetadata(video)
    expect(video.currentTime).toBe(4)
    fireEvent.click(screen.getByRole('button', { name: 'Add event' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add event' }))
    const starts = screen.getAllByLabelText('Start time (seconds, optional)')
    const ends = screen.getAllByLabelText('End time (seconds, optional)')
    expect(starts).toHaveLength(2)
    for (const input of [...starts, ...ends]) expect(input).toHaveValue(null)
    for (const input of screen.getAllByLabelText(/Event type \/ category/))
      expect(input).toHaveValue('')
    fireEvent.change(screen.getAllByLabelText(/Visible observation/)[0], {
      target: { value: 'A synthetic shape is visible.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save annotations locally' }))
    await screen.findByText('Annotations saved locally.')
    const saved = vi.mocked(saveAnnotation).mock.calls[0][1]
    expect(saved.events).toHaveLength(2)
    expect(saved.events[0].start_sec).toBeNull()
    expect(saved.events[0].end_sec).toBeNull()
    expect(saved.events[0].candidate_rule_id).toBeNull()
    expect(saved.events[0].event_type).toBe('')
    expect('timestamp_sec' in saved).toBe(false)
  })

  it('rejects invented interval boundaries beyond the video and preserves unsaved edits', async () => {
    render(<ReviewPage enabled />)
    fireEvent.click(await screen.findByRole('button', { name: 'Add event' }))
    fireEvent.change(screen.getByLabelText('End time (seconds, optional)'), {
      target: { value: '40' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save annotations locally' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('within the video duration')
    expect(saveAnnotation).not.toHaveBeenCalled()
    expect(screen.getByLabelText('End time (seconds, optional)')).toHaveValue(40)
  })

  it('shows save conflicts honestly without clearing the draft', async () => {
    vi.mocked(saveAnnotation).mockRejectedValue(
      new Error('This annotation changed in another tab. Reload before saving.'),
    )
    render(<ReviewPage enabled />)
    await screen.findByRole('button', { name: 'Add event' })
    fireEvent.change(screen.getByLabelText('Review notes'), { target: { value: 'Keep my draft.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save annotations locally' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('another tab'))
    expect(screen.getByLabelText('Review notes')).toHaveValue('Keep my draft.')
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument()
  })

  it('never loads organizer labels on the public application route', () => {
    render(<ReviewPage enabled={false} />)
    expect(screen.getByText(/explicitly enabled local review server/)).toBeInTheDocument()
    expect(getReviewItems).not.toHaveBeenCalled()
  })
})
