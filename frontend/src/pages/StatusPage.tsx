import { useStatus } from '../app/StatusContext'
import { Icon } from '../components/Icon'
import { t } from '../locales/en'
export function StatusPage() {
  const { status, error, refresh } = useStatus()
  const rows = status
    ? [
        {
          label: t.backend,
          good: status.backend_available,
          value: status.backend_available ? t.available : t.missing,
        },
        {
          label: t.worker,
          good: status.worker_alive,
          value: status.worker_alive ? t.running : t.notRunning,
        },
        {
          label: t.ffmpeg,
          good: status.ffmpeg_available,
          value: status.ffmpeg_available ? t.available : t.missing,
        },
        {
          label: t.detector,
          good: status.detector_name !== 'unconfigured',
          value: status.detector_name || t.unconfigured,
        },
        {
          label: t.model,
          good: status.model_available,
          value: status.model_available ? t.available : t.missing,
        },
        {
          label: t.ruleCount,
          good: status.active_verified_rules > 0,
          value: status.active_verified_rules.toString(),
        },
      ]
    : []
  return (
    <div className="page">
      <div className="page-heading heading-with-actions">
        <div>
          <p className="eyebrow">{t.statusEyebrow}</p>
          <h1>{t.statusTitle}</h1>
          <p className="lede">{t.statusDescription}</p>
        </div>
        <button className="button secondary" onClick={refresh}>
          <Icon name="status" size={17} />
          {t.refresh}
        </button>
      </div>
      {error ? (
        <div role="alert" className="error-message">
          <Icon name="alert" />
          {error}
        </div>
      ) : !status ? (
        <p role="status">{t.loading}</p>
      ) : (
        <>
          <div className={`status-summary ${status.ready ? 'ready' : 'pending'}`}>
            <Icon name={status.ready ? 'check' : 'alert'} size={27} />
            <div>
              <h2>{status.ready ? t.ready : t.setupNotice}</h2>
              <p>{status.ready ? t.readyDescription : t.setupDetail}</p>
            </div>
          </div>
          <div className="status-layout">
            <section className="card status-table">
              {rows.map((row) => (
                <div className="status-row" key={row.label}>
                  <span>{row.label}</span>
                  <strong className={row.good ? 'good' : 'pending'}>
                    <Icon name={row.good ? 'check' : 'alert'} size={17} />
                    {row.value}
                  </strong>
                </div>
              ))}
            </section>
            <aside className="card next-steps">
              <h2>{t.prerequisites}</h2>
              {status.reasons.length ? (
                <ul>
                  {status.reasons.map((reason, index) => (
                    <li key={index}>{reason}</li>
                  ))}
                </ul>
              ) : (
                <p>{t.readyDescription}</p>
              )}
              <div className="limits-panel">
                <h3>{t.configuredLimits}</h3>
                <p>{t.limits(status.limits.max_upload_mb, status.limits.max_video_seconds)}</p>
              </div>
              <a className="source-link" href="/docs" target="_blank" rel="noopener noreferrer">
                {t.apiDocs}
                <Icon name="external" size={14} />
              </a>
            </aside>
          </div>
        </>
      )}
      <p className="page-note">
        <Icon name="lock" size={17} />
        {t.privacyStatus}
      </p>
    </div>
  )
}
