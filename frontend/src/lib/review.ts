import { ApiError } from './api'
import { reviewText } from '../locales/review'

export interface AnnotationEvent {
  id: string
  event_type: string
  observation: string
  start_sec: number | null
  end_sec: number | null
  candidate_rule_id: string | null
  status: 'draft' | 'reviewed'
}
export interface Annotation {
  revision: number
  status: 'draft' | 'reviewed'
  events: AnnotationEvent[]
  notes: string
}
export interface ReviewItem {
  id: string
  filename: string
  has_violation: boolean
  timestamp_sec: number | null
  duration_sec: number
  review_status: 'draft' | 'reviewed'
  event_count: number
}
export interface ReviewDetail {
  source: ReviewItem
  annotation: Annotation
  video_url: string
}

export const isLocalReviewHost = () =>
  ['127.0.0.1', 'localhost', '[::1]'].includes(window.location.hostname) &&
  window.location.port === '8001'

async function reviewRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api/review${path}`, { credentials: 'same-origin', ...init })
  } catch {
    throw new ApiError(reviewText.unavailable, 0)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(
      typeof body?.detail === 'string' ? body.detail : reviewText.error,
      response.status,
    )
  }
  return response.json() as Promise<T>
}

let reviewSession: Promise<{ csrf_token: string }> | undefined
function session() {
  return (reviewSession ??= reviewRequest<{ csrf_token: string }>('/session').catch((error) => {
    reviewSession = undefined
    throw error
  }))
}
export async function getReviewItems() {
  await session()
  return reviewRequest<{ items: ReviewItem[]; excluded_count: number }>('/items')
}
export async function getReviewItem(id: string) {
  await session()
  return reviewRequest<ReviewDetail>(`/items/${encodeURIComponent(id)}`)
}
export async function saveAnnotation(id: string, annotation: Annotation) {
  const { csrf_token } = await session()
  return reviewRequest<{ annotation: Annotation }>(`/items/${encodeURIComponent(id)}/annotation`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf_token },
    body: JSON.stringify(annotation),
  })
}
