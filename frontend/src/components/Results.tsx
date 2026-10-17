import { useRef, useState } from 'react'
import type { Evidence, Job, ReviewEvent } from '../lib/types'
import { readable, timecode } from '../lib/format'
import { t } from '../locales/en'
import { Icon } from './Icon'
import { RuleSource } from './RuleSource'
import { EvidenceDialog } from './EvidenceDialog'
import { EvidenceImage } from './EvidenceImage'
export function Results({ job }: { job: Job }) {
  const result = job.result!
  const events = [...result.events].sort(
    (a, b) => a.timecode_sec - b.timecode_sec || a.id.localeCompare(b.id),
  )
  const [selectedId, setSelectedId] = useState<string | null>(events[0]?.id ?? null)
  const [frame, setFrame] = useState<Evidence | null>(null)
  const [previewError, setPreviewError] = useState(false)
  const video = useRef<HTMLVideoElement>(null)
  const pendingSeek = useRef<number | null>(null)
  const selected = events.find((e) => e.id === selectedId)
  const positive = result.verdict === 'violation'
  // Separate nearby markers into rows so simultaneous findings remain clickable.
  const laneEnds: number[] = []
  const markers = events.map((event) => {
    const position = Math.min(98, Math.max(2, (event.timecode_sec / result.duration_sec) * 100))
    const available = laneEnds.findIndex((end) => position - end >= 11)
    const lane = available < 0 ? laneEnds.length : available
    laneEnds[lane] = position
    return { event, lane, position }
  })
  function select(event: ReviewEvent) {
    setSelectedId(event.id)
    pendingSeek.current = event.timecode_sec
    if (video.current) {
      video.current.currentTime = event.timecode_sec
      if (video.current.readyState >= 1) pendingSeek.current = null
    }
  }
  return (
    <>
      <div className={`verdict-banner ${positive ? 'positive' : 'negative'}`}>
        <div className="verdict-icon">
          <Icon name={positive ? 'alert' : 'check'} size={24} />
        </div>
        <div>
          <h2>{positive ? t.positive : t.negative}</h2>
          <p>{positive ? t.human : t.negativeQualifier}</p>
        </div>
        <span className="verdict-tag">
          {positive ? t.eventsCount(events.length) : t.reviewRequired}
        </span>
      </div>
      <div className="results-layout">
        <div className="evidence-column">
          <section className="card player-card">
            <div className="section-title">
              <h2>{t.video}</h2>
              <span className="timecode muted">{timecode(result.duration_sec)}</span>
            </div>
            <div className="video-stage">
              {result.preview_available && result.preview_url && !previewError ? (
                <video
                  ref={video}
                  src={result.preview_url}
                  controls
                  playsInline
                  preload="metadata"
                  aria-label={t.video}
                  onError={() => setPreviewError(true)}
                  onLoadedMetadata={() => {
                    if (pendingSeek.current !== null && video.current) {
                      video.current.currentTime = pendingSeek.current
                      pendingSeek.current = null
                    }
                  }}
                />
              ) : (
                <div className="preview-empty">
                  <Icon name="video" size={38} />
                  <p>{t.noPreview}</p>
                </div>
              )}
            </div>
            <div
              className="timeline"
              role="group"
              aria-label={t.timeline}
              style={{ height: `${Math.max(1, laneEnds.length) * 30 + 26}px` }}
            >
              {Array.from({ length: Math.max(1, laneEnds.length) }, (_, lane) => (
                <div className="timeline-track" key={lane} style={{ top: `${lane * 30 + 15}px` }} />
              ))}
              {markers.map(({ event, lane, position }, index) => (
                <button
                  key={event.id}
                  className={`timeline-marker ${selectedId === event.id ? 'selected' : ''}`}
                  style={{
                    left: `${position}%`,
                    top: `${lane * 30 + 3}px`,
                  }}
                  onClick={() => select(event)}
                  aria-label={t.eventLabel(event.type, timecode(event.timecode_sec), index)}
                  aria-pressed={selectedId === event.id}
                >
                  <span>{index + 1}</span>
                </button>
              ))}
              <div className="timeline-labels">
                <span>00:00</span>
                <span>{timecode(result.duration_sec)}</span>
              </div>
            </div>
          </section>
          {selected ? (
            <section className="card event-inspector">
              <div className="section-title">
                <div>
                  <p className="eyebrow">{t.evidence}</p>
                  <h2>{selected.type}</h2>
                </div>
                <span className="timestamp-pill">{timecode(selected.timecode_sec)}</span>
              </div>
              <div className="evidence-grid">
                {selected.evidence_frames.map((item, index) => (
                  <button
                    className="evidence-thumb"
                    key={`${selected.id}-${index}`}
                    onClick={() => setFrame(item)}
                    aria-label={`${t.enlarge} ${timecode(item.timestamp_sec)}`}
                  >
                    <EvidenceImage frame={item} />
                    <span>
                      <span className="timecode">{timecode(item.timestamp_sec)}</span>
                      <Icon name="expand" size={16} />
                    </span>
                  </button>
                ))}
              </div>
              <div className="inspector-copy">
                <div>
                  <h3>{t.observation}</h3>
                  <p>{selected.observation}</p>
                </div>
                <div>
                  <h3>{t.interpretation}</h3>
                  <p>{selected.interpretation}</p>
                </div>
                <div>
                  <h3>{t.ruleSource}</h3>
                  <RuleSource rule={selected.rule} />
                </div>
                <div>
                  <h3>{t.limitations}</h3>
                  <ul className="limitations-list">
                    {selected.limitations.map((item, index) => (
                      <li key={index}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </section>
          ) : (
            <section className="card empty-events">
              <Icon name="check" size={28} />
              <h2>{t.noEvents}</h2>
              <p>{t.noEventsBody}</p>
            </section>
          )}
          <section className="card coverage-card">
            <h2>{t.coverage}</h2>
            {Array.isArray(result.coverage) ? (
              <ul>
                {result.coverage.map((item, index) => (
                  <li key={index}>{readable(item)}</li>
                ))}
              </ul>
            ) : typeof result.coverage === 'object' ? (
              <dl>
                {Object.entries(result.coverage).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key.replaceAll('_', ' ')}</dt>
                    <dd>{readable(value)}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p>{readable(result.coverage)}</p>
            )}
            {result.unmapped_observations.length > 0 && (
              <details>
                <summary>
                  {t.unmapped} ({result.unmapped_observations.length})
                </summary>
                <p>{t.unmappedBody}</p>
                <ul>
                  {result.unmapped_observations.map((item, index) => (
                    <li key={index}>{readable(item)}</li>
                  ))}
                </ul>
              </details>
            )}
          </section>
        </div>
        <aside className="card event-list">
          <div className="section-title">
            <div>
              <h2>{t.events}</h2>
              <p>{t.ordered}</p>
            </div>
            <span className="count-pill">{events.length}</span>
          </div>
          {events.length ? (
            events.map((event, index) => (
              <button
                className={`event-item ${event.id === selectedId ? 'selected' : ''}`}
                key={event.id}
                onClick={() => select(event)}
                aria-label={t.eventReviewLabel(event.type, timecode(event.timecode_sec), index)}
                aria-pressed={event.id === selectedId}
              >
                <div className="event-item-top">
                  <span className="event-number">{String(index + 1).padStart(2, '0')}</span>
                  <span className="timecode">{timecode(event.timecode_sec)}</span>
                </div>
                <strong>{event.type}</strong>
                <p>{event.observation}</p>
                <Icon name="chevron" size={16} />
              </button>
            ))
          ) : (
            <p className="event-list-empty">{t.noEvents}</p>
          )}
          <div className="event-list-footer">
            <Icon name="rules" size={17} />
            <span>{t.human}</span>
          </div>
        </aside>
      </div>
      {frame && <EvidenceDialog frame={frame} onClose={() => setFrame(null)} />}
    </>
  )
}
