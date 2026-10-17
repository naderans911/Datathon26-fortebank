import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError, deleteJob, getJob } from '../lib/api'
import type { Job } from '../lib/types'
import { timecode } from '../lib/format'
import { Icon } from '../components/Icon'
import { Results } from '../components/Results'
import { t } from '../locales/en'
const stageOrder = [
  'validating',
  'preparing_frames',
  'analyzing',
  'checking_rules',
  'preparing_evidence',
] as const
export function JobView({ job }: { job: Job }) {
  const [elapsed, setElapsed] = useState(job.elapsed_sec)
  useEffect(() => {
    if (job.status !== 'processing') return
    const tick = () => setElapsed(Math.max(job.elapsed_sec, Date.now() / 1000 - job.created_at))
    tick()
    const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [job.status, job.created_at, job.elapsed_sec])
  if (job.status === 'failed')
    return (
      <section className="card failure-card" role="alert">
        <div className="error-symbol">
          <Icon name="alert" size={32} />
        </div>
        <h2>{t.failedTitle}</h2>
        <p>{t.failedBody}</p>
        <div className="error-detail">
          <code>{job.error?.code}</code>
          <p>{job.error?.message || t.errorGeneric}</p>
        </div>
        <Link className="button secondary" to="/">
          {t.back}
          <Icon name="arrow" size={17} />
        </Link>
      </section>
    )
  if (job.status === 'done' && job.result) return <Results job={job} />
  if (job.status === 'done')
    return (
      <div role="alert" className="error-message">
        {t.failedBody}
      </div>
    )
  const aliases: Record<string, string> = {
    validating_video: 'validating',
    analyzing_activity: 'analyzing',
    mapping_rules: 'checking_rules',
    checking_rule_mappings: 'checking_rules',
  }
  const stage = aliases[job.stage] || job.stage
  const active = stageOrder.indexOf(stage as (typeof stageOrder)[number])
  return (
    <section className="card processing-card">
      <div className="processing-top">
        <div className="processing-spinner" />
        <span className="small-label">{t.processingTitle}</span>
        <h2>{t.stages[job.stage as keyof typeof t.stages] || t.queued}</h2>
        <p>{t.processingBody}</p>
        <div className="elapsed">
          <Icon name="clock" size={18} />
          {t.elapsed}
          <strong className="timecode">{timecode(elapsed)}</strong>
        </div>
      </div>
      <ol className="processing-stages">
        {stageOrder.map((key, index) => (
          <li key={key} className={index < active ? 'complete' : index === active ? 'current' : ''}>
            <span>{index < active ? <Icon name="check" size={15} /> : index + 1}</span>
            {t.stages[key]}
            {index === active && <span className="stage-current-dot" />}
          </li>
        ))}
      </ol>
      <p className="helper">{t.progressNote}</p>
      <p className="helper">{t.recovery}</p>
    </section>
  )
}
export function AnalysisPage() {
  const { jobId } = useParams()
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [deleting, setDeleting] = useState(false)
  const navigate = useNavigate()
  useEffect(() => {
    let disposed = false
    let timer: ReturnType<typeof setTimeout>
    setJob(null)
    setError('')
    async function poll() {
      try {
        const data = await getJob(jobId!)
        if (disposed) return
        setJob(data)
        setError('')
        if (data.status === 'processing') timer = setTimeout(poll, 2000)
      } catch (e) {
        if (disposed) return
        setError(
          e instanceof ApiError && [403, 404].includes(e.status)
            ? t.jobUnavailable
            : e instanceof Error
              ? e.message
              : t.errorGeneric,
        )
      }
    }
    void poll()
    return () => {
      disposed = true
      clearTimeout(timer)
    }
  }, [jobId, attempt])
  async function remove() {
    if (!job || !window.confirm(t.deleteConfirm)) return
    setDeleting(true)
    try {
      await deleteJob(job.job_id)
      navigate('/')
    } catch (e) {
      setError(e instanceof Error ? e.message : t.errorGeneric)
      setDeleting(false)
    }
  }
  return (
    <div className="page analysis-page">
      <div className="page-heading heading-with-actions">
        <div>
          <p className="eyebrow">{t.resultEyebrow}</p>
          <h1>{job?.status === 'processing' ? t.processingTitle : t.resultTitle}</h1>
          {job && (
            <p className="job-meta">
              {job.filename}
              <span>
                {t.jobId}: {job.job_id}
              </span>
            </p>
          )}
        </div>
        <Link className="button secondary" to="/">
          {t.newAnalysis}
          <Icon name="upload" size={16} />
        </Link>
      </div>
      {job?.demo && (
        <div className="demo-banner">
          <Icon name="alert" size={17} />
          {t.demo}
        </div>
      )}
      {error && (
        <div className="error-message" role="alert">
          <Icon name="alert" />
          {error}
          <button className="text-button" onClick={() => setAttempt((a) => a + 1)}>
            {t.reload}
          </button>
        </div>
      )}
      {!job && !error && <p role="status">{t.loading}</p>}
      {job && <JobView key={job.job_id} job={job} />}
      {job && job.status !== 'processing' && (
        <div className="delete-row">
          <button className="text-button muted" disabled={deleting} onClick={remove}>
            <Icon name="trash" size={16} />
            {deleting ? t.deleting : t.delete}
          </button>
        </div>
      )}
    </div>
  )
}
