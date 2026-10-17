import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useStatus } from '../app/StatusContext'
import { Icon } from '../components/Icon'
import { uploadVideo } from '../lib/api'
import { fileSize, timecode, validateFile } from '../lib/format'
import { t } from '../locales/en'
export function UploadPage() {
  const { status, error: statusError } = useStatus()
  const navigate = useNavigate()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [duration, setDuration] = useState<number | null>(null)
  const [unsupported, setUnsupported] = useState(false)
  const [busy, setBusy] = useState(false)
  const [drag, setDrag] = useState(false)
  const limitMb = status?.limits.max_upload_mb ?? 100
  const maxSeconds = status?.limits.max_video_seconds ?? 300
  useEffect(() => {
    if (!file) return
    const url = URL.createObjectURL(file)
    const video = document.createElement('video')
    video.preload = 'metadata'
    const timer = setTimeout(() => setUnsupported(true), 6000)
    video.onloadedmetadata = () => {
      clearTimeout(timer)
      if (Number.isFinite(video.duration)) {
        setDuration(video.duration)
        setUnsupported(false)
      } else setUnsupported(true)
    }
    video.onerror = () => {
      clearTimeout(timer)
      setUnsupported(true)
    }
    video.src = url
    return () => {
      clearTimeout(timer)
      video.onloadedmetadata = null
      video.onerror = null
      video.removeAttribute('src')
      URL.revokeObjectURL(url)
    }
  }, [file])
  const fileError = file ? validateFile(file, limitMb) : null
  const durationError = duration !== null && duration > maxSeconds ? t.tooLong(maxSeconds) : null
  const choose = (selected: File | undefined) => {
    if (!selected) return
    setError('')
    setDuration(null)
    setUnsupported(false)
    const problem = validateFile(selected, limitMb)
    if (problem) {
      setFile(null)
      setError(problem)
      return
    }
    setFile(selected)
  }
  async function submit() {
    if (!file || !status?.ready || fileError || durationError || busy) return
    setBusy(true)
    setError('')
    try {
      const job = await uploadVideo(file)
      navigate(`/analysis/${encodeURIComponent(job.job_id)}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : t.errorGeneric)
      setBusy(false)
    }
  }
  return (
    <div className="page upload-page">
      <div className="page-heading">
        <p className="eyebrow">{t.eyebrow}</p>
        <h1>{t.uploadTitle}</h1>
        <p className="lede">{t.uploadDescription}</p>
      </div>
      <div className="upload-layout">
        <section className="card upload-card">
          <div className="card-heading">
            <div>
              <h2>{t.upload}</h2>
              <p>{t.uploadHelper}</p>
            </div>
            <span className="step-badge">01</span>
          </div>
          <input
            ref={input}
            className="sr-only"
            type="file"
            id="video-file"
            accept=".mov,.mp4,.m4v,.mkv"
            aria-label={t.fileInput}
            disabled={busy}
            onChange={(e) => choose(e.target.files?.[0])}
          />
          <div
            className={`dropzone ${drag ? 'dragging' : ''} ${file ? 'has-file' : ''}`}
            onDragOver={(e) => {
              e.preventDefault()
              if (!busy) setDrag(true)
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDrag(false)
              if (!busy) choose(e.dataTransfer.files[0])
            }}
          >
            {file ? (
              <>
                <div className="upload-icon">
                  <Icon name="video" size={29} />
                </div>
                <span className="small-label">{t.selected}</span>
                <h3 className="filename">{file.name}</h3>
                <div className="file-meta">
                  <span>{fileSize(file.size)}</span>
                  <span>{duration !== null ? timecode(duration) : t.durationUnknown}</span>
                </div>
                <div className="file-actions">
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() => input.current?.click()}
                  >
                    {t.replace}
                  </button>
                  <span className="muted">·</span>
                  <button
                    className="text-button muted"
                    disabled={busy}
                    onClick={() => {
                      setFile(null)
                      setDuration(null)
                      setUnsupported(false)
                      if (input.current) input.current.value = ''
                    }}
                  >
                    {t.remove}
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="upload-icon">
                  <Icon name="upload" size={30} />
                </div>
                <h3>{t.dropTitle}</h3>
                <p>{t.dropSub}</p>
                <button className="button secondary" onClick={() => input.current?.click()}>
                  {t.browse}
                  <Icon name="arrow" size={16} />
                </button>
                <div className="upload-limits">
                  <strong>{t.formats}</strong>
                  <span>{t.limits(limitMb, maxSeconds)}</span>
                </div>
              </>
            )}
          </div>
          {unsupported && (
            <p className="inline-notice">
              <Icon name="video" size={18} />
              {t.previewUnsupported}
            </p>
          )}
          {(error || fileError || durationError) && (
            <p role="alert" className="error-message">
              <Icon name="alert" size={18} />
              {error || fileError || durationError}
            </p>
          )}
          <div className="upload-action">
            <div className="privacy-inline">
              <Icon name="lock" size={17} />
              <span>{t.privacy}</span>
            </div>
            <button
              className="button primary"
              disabled={!file || !status?.ready || !!fileError || !!durationError || busy}
              onClick={submit}
            >
              {busy ? t.uploading : t.analyze}
              <Icon name="arrow" size={18} />
            </button>
          </div>
          {busy && (
            <p className="helper" role="status">
              {t.uploadPending}
            </p>
          )}
          {!status?.ready && (
            <div className="setup-notice">
              <Icon name="alert" size={18} />
              <div>
                <strong>{statusError ? t.unavailable : t.setupNotice}</strong>
                <p>{statusError || t.setupDetail}</p>
                <Link to="/status">
                  {t.checkStatus}
                  <Icon name="arrow" size={14} />
                </Link>
              </div>
            </div>
          )}
        </section>
        <aside className="workflow-panel">
          <p className="eyebrow">{t.whatNext}</p>
          <ol className="workflow">
            {t.workflow.map((step, index) => (
              <li key={step.title}>
                <span className="workflow-number">{index + 1}</span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
          <div className="review-note">
            <Icon name="rules" size={23} />
            <h3>{t.scopeTitle}</h3>
            <p>{t.scopeBody}</p>
          </div>
          {status?.demo_enabled && (
            <Link className="demo-link" to="/demo">
              {t.demoLink}
              <Icon name="arrow" size={16} />
            </Link>
          )}
        </aside>
      </div>
      <div className="page-note">
        <Icon name="lock" size={17} />
        <span>{t.privacyDetail}</span>
      </div>
    </div>
  )
}
