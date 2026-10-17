import { useCallback, useEffect, useRef, useState } from 'react'
import { Icon } from '../components/Icon'
import { timecode } from '../lib/format'
import { getReviewItem, getReviewItems, isLocalReviewHost, saveAnnotation } from '../lib/review'
import type { Annotation, AnnotationEvent, ReviewDetail, ReviewItem } from '../lib/review'
import { reviewText as r } from '../locales/review'

export function ReviewPage({ enabled = isLocalReviewHost() }: { enabled?: boolean }) {
  const [items, setItems] = useState<ReviewItem[]>([])
  const [excluded, setExcluded] = useState(0)
  const [query, setQuery] = useState('')
  const [detail, setDetail] = useState<ReviewDetail | null>(null)
  const [annotation, setAnnotation] = useState<Annotation | null>(null)
  const [loading, setLoading] = useState(enabled)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [previewError, setPreviewError] = useState(false)
  const [previewReady, setPreviewReady] = useState(false)
  const [previewVersion, setPreviewVersion] = useState(0)
  const player = useRef<HTMLVideoElement>(null)
  const pendingSeek = useRef<number | null>(null)
  const generation = useRef(0)
  const cancelPending = useCallback(() => {
    generation.current++
  }, [])

  const open = useCallback(async (id: string) => {
    const request = ++generation.current
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const next = await getReviewItem(id)
      if (request !== generation.current) return
      setDetail(next)
      setAnnotation(next.annotation)
      setDirty(false)
      setPreviewError(false)
      setPreviewReady(false)
      setPreviewVersion((version) => version + 1)
      pendingSeek.current = next.source.timestamp_sec
    } catch (failure) {
      if (request === generation.current) setError((failure as Error).message)
    } finally {
      if (request === generation.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    let active = true
    getReviewItems()
      .then(async (data) => {
        if (!active) return
        setItems(data.items)
        setExcluded(data.excluded_count)
        if (data.items.length) await open(data.items[0].id)
        else setLoading(false)
      })
      .catch((failure) => {
        if (active) {
          setError(failure.message)
          setLoading(false)
        }
      })
    return () => {
      active = false
      cancelPending()
    }
  }, [enabled, open, cancelPending])

  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  function edit(next: Annotation) {
    setAnnotation(next)
    setDirty(true)
    setMessage('')
  }
  function editEvent(id: string, changes: Partial<AnnotationEvent>) {
    if (!annotation) return
    edit({
      ...annotation,
      events: annotation.events.map((event) =>
        event.id === id ? { ...event, ...changes } : event,
      ),
    })
  }
  function seek(seconds: number, play = false) {
    const target = Math.max(0, Math.min(seconds, detail?.source.duration_sec ?? 0))
    pendingSeek.current = target
    if (player.current && player.current.readyState >= 1) {
      player.current.currentTime = target
      pendingSeek.current = null
      if (play) void player.current.play().catch(() => setError(r.previewError))
    }
  }
  async function save() {
    if (!detail || !annotation) return
    const invalidBoundary = annotation.events.some(
      (event) =>
        [event.start_sec, event.end_sec].some(
          (value) =>
            value !== null &&
            (!Number.isFinite(value) || value < 0 || value > detail.source.duration_sec),
        ) ||
        (event.start_sec !== null && event.end_sec !== null && event.end_sec < event.start_sec),
    )
    if (invalidBoundary) {
      setError(r.boundaryError)
      return
    }
    if (
      annotation.events.some((event) => event.status === 'reviewed' && !event.observation.trim()) ||
      (annotation.status === 'reviewed' &&
        annotation.events.some((event) => event.status !== 'reviewed'))
    ) {
      setError(r.reviewedError)
      return
    }
    setSaving(true)
    setError('')
    try {
      const result = await saveAnnotation(detail.source.id, annotation)
      setAnnotation(result.annotation)
      setDirty(false)
      setMessage(r.saved)
      setItems((current) =>
        current.map((item) =>
          item.id === detail.source.id
            ? {
                ...item,
                review_status: result.annotation.status,
                event_count: result.annotation.events.length,
              }
            : item,
        ),
      )
    } catch (failure) {
      setError((failure as Error).message)
    } finally {
      setSaving(false)
    }
  }
  const filtered = items.filter((item) => item.filename.toLowerCase().includes(query.toLowerCase()))
  return (
    <div className="page review-page">
      <div className="page-heading">
        <p className="eyebrow">{r.eyebrow}</p>
        <h1>{r.title}</h1>
        <p>{r.description}</p>
      </div>
      <div className="demo-banner">
        <Icon name="lock" />
        <p>{r.isolation}</p>
      </div>
      {!enabled ? (
        <div className="card review-notice">{r.blocked}</div>
      ) : (
        <>
          {error && (
            <div role="alert" className="error-message">
              {error}
            </div>
          )}
          {excluded > 0 && <div className="inline-notice">{r.excluded(excluded)}</div>}
          {loading && !detail && <p role="status">{r.loading}</p>}
          {!loading && !items.length && !error && (
            <div className="card review-notice">{r.empty}</div>
          )}
          <div className="annotation-layout">
            <aside className="card review-catalog">
              <h2>{r.records}</h2>
              <label className="review-field">
                <span>{r.search}</span>
                <input
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </label>
              <div className="review-records">
                {filtered.map((item) => (
                  <button
                    key={item.id}
                    className={`review-record ${detail?.source.id === item.id ? 'selected' : ''}`}
                    aria-label={r.open(item.filename)}
                    aria-pressed={detail?.source.id === item.id}
                    disabled={saving || loading}
                    onClick={() => {
                      if (!dirty || window.confirm(r.discard)) void open(item.id)
                    }}
                  >
                    <strong>{item.filename}</strong>
                    <span>
                      {item.review_status === 'reviewed' ? r.reviewed : r.draft} ·{' '}
                      {item.event_count}
                    </span>
                  </button>
                ))}
              </div>
            </aside>
            {detail && annotation && (
              <div className="annotation-main" aria-busy={loading || saving}>
                <section className="card review-player">
                  <div className="section-title">
                    <h2>{detail.source.filename}</h2>
                    <button
                      type="button"
                      className="text-button"
                      disabled={loading || saving}
                      onClick={() => {
                        if (!dirty || window.confirm(r.reloadConfirm)) void open(detail.source.id)
                      }}
                    >
                      {r.reload}
                    </button>
                  </div>
                  <div className="review-source">
                    <strong>{r.original}</strong>
                    <dl>
                      <div>
                        <dt>{r.original}</dt>
                        <dd>{detail.source.has_violation ? r.positive : r.negative}</dd>
                      </div>
                      <div>
                        <dt>{r.point}</dt>
                        <dd>
                          {detail.source.timestamp_sec === null
                            ? r.noPoint
                            : timecode(detail.source.timestamp_sec)}
                        </dd>
                      </div>
                      <div>
                        <dt>{r.duration}</dt>
                        <dd>{timecode(detail.source.duration_sec)}</dd>
                      </div>
                    </dl>
                    <p>{r.pointNote}</p>
                  </div>
                  <div className="video-stage">
                    {previewError ? (
                      <p className="review-notice">{r.previewError}</p>
                    ) : (
                      <video
                        key={`${detail.source.id}-${previewVersion}`}
                        ref={player}
                        src={detail.video_url}
                        controls
                        preload="auto"
                        playsInline
                        aria-label={r.player}
                        onError={() => setPreviewError(true)}
                        onLoadedMetadata={() => {
                          setPreviewReady(true)
                          if (pendingSeek.current !== null && player.current) {
                            player.current.currentTime = pendingSeek.current
                            pendingSeek.current = null
                          }
                        }}
                      />
                    )}
                  </div>
                  {!previewReady && !previewError && (
                    <p role="status" className="review-preview-status">
                      {r.previewLoading}
                    </p>
                  )}
                  <div className="review-playback">
                    <button
                      className="button secondary"
                      disabled={!previewReady || detail.source.timestamp_sec === null}
                      onClick={() => seek(detail.source.timestamp_sec!)}
                    >
                      {r.jump}
                    </button>
                    <button
                      className="button secondary"
                      disabled={!previewReady || detail.source.timestamp_sec === null}
                      onClick={() => seek(detail.source.timestamp_sec! - 5, true)}
                    >
                      {r.context}
                    </button>
                    <button
                      className="text-button"
                      disabled={!previewReady}
                      onClick={() => seek((player.current?.currentTime ?? 0) - 5)}
                    >
                      {r.rewind}
                    </button>
                    <button
                      className="text-button"
                      disabled={!previewReady}
                      onClick={() => seek((player.current?.currentTime ?? 0) + 5)}
                    >
                      {r.forward}
                    </button>
                  </div>
                </section>
                <section className="card annotation-editor">
                  <div className="section-title">
                    <div>
                      <h2>{r.annotations}</h2>
                      <p>{r.separate}</p>
                    </div>
                    <button
                      className="button secondary"
                      disabled={saving || loading}
                      onClick={() =>
                        edit({
                          ...annotation,
                          events: [
                            ...annotation.events,
                            {
                              id: crypto.randomUUID(),
                              event_type: '',
                              observation: '',
                              start_sec: null,
                              end_sec: null,
                              candidate_rule_id: null,
                              status: 'draft',
                            },
                          ],
                        })
                      }
                    >
                      {r.add}
                    </button>
                  </div>
                  <fieldset disabled={saving || loading} className="annotation-fields">
                    {!annotation.events.length && <p className="muted">{r.noEvents}</p>}
                    {annotation.events.map((event, index) => (
                      <section key={event.id} className="annotation-event">
                        <div className="section-title">
                          <h3>{r.event(index)}</h3>
                          <button
                            type="button"
                            className="text-button"
                            aria-label={r.remove(index)}
                            onClick={() =>
                              edit({
                                ...annotation,
                                events: annotation.events.filter((other) => other.id !== event.id),
                              })
                            }
                          >
                            {r.remove(index)}
                          </button>
                        </div>
                        <label className="review-field">
                          <span>{r.type}</span>
                          <input
                            value={event.event_type}
                            maxLength={200}
                            onChange={(change) =>
                              editEvent(event.id, { event_type: change.target.value })
                            }
                          />
                          <small>{r.typeHint}</small>
                        </label>
                        <label className="review-field">
                          <span>{r.observation}</span>
                          <textarea
                            rows={3}
                            maxLength={4000}
                            value={event.observation}
                            onChange={(change) =>
                              editEvent(event.id, { observation: change.target.value })
                            }
                          />
                          <small>{r.observationHint}</small>
                        </label>
                        <div className="boundary-fields">
                          <label className="review-field">
                            <span>{r.start}</span>
                            <input
                              type="number"
                              min={0}
                              max={detail.source.duration_sec}
                              step="0.1"
                              value={event.start_sec ?? ''}
                              onChange={(change) =>
                                editEvent(event.id, {
                                  start_sec:
                                    change.target.value === '' ? null : change.target.valueAsNumber,
                                })
                              }
                            />
                          </label>
                          <label className="review-field">
                            <span>{r.end}</span>
                            <input
                              type="number"
                              min={0}
                              max={detail.source.duration_sec}
                              step="0.1"
                              value={event.end_sec ?? ''}
                              onChange={(change) =>
                                editEvent(event.id, {
                                  end_sec:
                                    change.target.value === '' ? null : change.target.valueAsNumber,
                                })
                              }
                            />
                          </label>
                        </div>
                        <p className="field-hint">{r.boundaryHint}</p>
                        <label className="review-field">
                          <span>{r.candidate}</span>
                          <input
                            maxLength={200}
                            value={event.candidate_rule_id ?? ''}
                            onChange={(change) =>
                              editEvent(event.id, {
                                candidate_rule_id: change.target.value || null,
                              })
                            }
                          />
                          <small>{r.candidateHint}</small>
                        </label>
                        <label className="review-field">
                          <span>{r.eventStatus}</span>
                          <select
                            value={event.status}
                            onChange={(change) =>
                              editEvent(event.id, {
                                status: change.target.value as AnnotationEvent['status'],
                              })
                            }
                          >
                            <option value="draft">{r.draft}</option>
                            <option value="reviewed">{r.reviewed}</option>
                          </select>
                        </label>
                      </section>
                    ))}
                    <label className="review-field">
                      <span>{r.notes}</span>
                      <textarea
                        rows={3}
                        maxLength={8000}
                        value={annotation.notes}
                        onChange={(event) => edit({ ...annotation, notes: event.target.value })}
                      />
                    </label>
                    <label className="review-field">
                      <span>{r.recordStatus}</span>
                      <select
                        value={annotation.status}
                        onChange={(event) =>
                          edit({
                            ...annotation,
                            status: event.target.value as Annotation['status'],
                          })
                        }
                      >
                        <option value="draft">{r.draft}</option>
                        <option value="reviewed">{r.reviewed}</option>
                      </select>
                    </label>
                  </fieldset>
                  <div className="annotation-save">
                    <span role="status">{message || (dirty ? r.unsaved : '')}</span>
                    <button
                      className="button primary"
                      disabled={!dirty || saving || loading}
                      onClick={() => void save()}
                    >
                      {saving ? r.saving : r.save}
                    </button>
                  </div>
                </section>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
