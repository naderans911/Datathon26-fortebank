export interface Rule {
  id: string
  title: string
  event_type: string
  jurisdiction: string
  source_type: string
  document_title: string
  source_url: string | null
  section_or_paragraph: string | null
  relevant_excerpt: string
  observed_condition: string
  required_context: string[]
  interpretation: string
  limitations: string[]
  verification_status: 'draft' | 'verified' | 'disabled'
  verified_at: string | null
  enabled: boolean
  version: string
}
export interface Evidence {
  timestamp_sec: number
  url: string
}
export interface ReviewEvent {
  id: string
  type: string
  timecode_sec: number
  observation: string
  interpretation: string
  rule: Rule | null
  limitations: string[]
  evidence_frames: Evidence[]
}
export interface Result {
  verdict: 'violation' | 'no_violation'
  duration_sec: number
  events: ReviewEvent[]
  unmapped_observations: unknown[]
  preview_available: boolean
  preview_url: string | null
  coverage: Record<string, unknown> | string[] | string
}
export interface Job {
  job_id: string
  status: 'processing' | 'done' | 'failed'
  stage: string
  created_at: number
  updated_at: number
  elapsed_sec: number
  filename: string
  size_bytes: number
  demo?: boolean
  error?: { code: string; message: string }
  result?: Result
}
export interface SystemStatus {
  ready: boolean
  backend_available: boolean
  worker_heartbeat: number | null
  worker_alive: boolean
  ffmpeg_available: boolean
  detector_name: string
  model_available: boolean
  active_verified_rules: number
  reasons: string[]
  limits: { max_upload_mb: number; max_video_seconds: number }
  demo_enabled: boolean
}
