import { t } from '../locales/en'
import type { Job, Rule, SystemStatus } from './types'
export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, { credentials: 'same-origin', ...init })
  } catch {
    throw new ApiError(t.unavailable, 0)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body?.detail
    throw new ApiError(
      typeof detail === 'string'
        ? detail
        : detail?.message || body?.error?.message || t.errorGeneric,
      response.status,
    )
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
let sessionPromise: Promise<{ csrf_token: string }> | undefined
export function session() {
  return (sessionPromise ??= request<{ csrf_token: string }>('/api/ui/session').catch((error) => {
    sessionPromise = undefined
    throw error
  }))
}
export const getStatus = () => request<SystemStatus>('/api/ui/status')
export const getRules = () => request<{ rules: Rule[] }>('/api/ui/rules')
export async function getJob(id: string) {
  await session()
  return request<Job>(`/api/ui/jobs/${encodeURIComponent(id)}`)
}
export async function getDemo(kind: string) {
  await session()
  return request<Job>(`/api/ui/demo/${encodeURIComponent(kind)}`)
}
export async function uploadVideo(file: File) {
  const { csrf_token } = await session()
  const body = new FormData()
  body.append('file', file)
  return request<{ job_id: string }>('/api/ui/analyze', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrf_token },
    body,
  })
}
export async function deleteJob(id: string) {
  const { csrf_token } = await session()
  return request<void>(`/api/ui/jobs/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: { 'X-CSRF-Token': csrf_token },
  })
}
