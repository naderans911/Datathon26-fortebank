import { useState } from 'react'
import type { Evidence } from '../lib/types'
import { timecode } from '../lib/format'
import { t } from '../locales/en'
import { Icon } from './Icon'
export function EvidenceImage({ frame }: { frame: Evidence }) {
  const [failed, setFailed] = useState(false)
  return failed ? (
    <span className="evidence-unavailable" role="status">
      <Icon name="alert" size={24} />
      <span>{t.evidenceUnavailable}</span>
    </span>
  ) : (
    <img
      src={frame.url}
      alt={t.frameAlt(timecode(frame.timestamp_sec))}
      onError={() => setFailed(true)}
    />
  )
}
