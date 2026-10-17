import { useState } from 'react'
import { useStatus } from '../app/StatusContext'
import { getDemo } from '../lib/api'
import type { Job } from '../lib/types'
import { JobView } from './AnalysisPage'
import { Icon } from '../components/Icon'
import { t } from '../locales/en'
export function DemoPage() {
  const { status } = useStatus()
  const [job, setJob] = useState<Job | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [kind, setKind] = useState('')
  async function load(value: string) {
    setBusy(true)
    setError('')
    setJob(null)
    setKind(value)
    try {
      setJob(await getDemo(value))
    } catch (e) {
      setError(e instanceof Error ? e.message : t.errorGeneric)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="page">
      <div className="page-heading">
        <p className="eyebrow">{t.synthetic}</p>
        <h1>{t.demoTitle}</h1>
        <p className="lede">{t.demoDescription}</p>
      </div>
      <div className="demo-banner">
        <Icon name="alert" size={19} />
        {t.demo}
      </div>
      {status && !status.demo_enabled ? (
        <section className="card empty-state">
          <h2>{t.demoDisabled}</h2>
          <p>{t.demoDisabledBody}</p>
        </section>
      ) : (
        <>
          <div className="demo-controls">
            {(
              [
                ['positive', t.demoPositive],
                ['negative', t.demoNegative],
                ['failed', t.demoFailed],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                className={`button ${kind === value ? 'primary' : 'secondary'}`}
                disabled={busy || !status}
                onClick={() => load(value)}
              >
                {label}
              </button>
            ))}
          </div>
          {busy && <p role="status">{t.loading}</p>}
          {error && (
            <div role="alert" className="error-message">
              {error}
            </div>
          )}
          {job && <JobView key={job.job_id} job={job} />}
        </>
      )}
    </div>
  )
}
