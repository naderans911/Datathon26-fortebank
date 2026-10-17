import { useEffect, useRef } from 'react'
import type { Evidence } from '../lib/types'
import { timecode } from '../lib/format'
import { t } from '../locales/en'
import { Icon } from './Icon'
import { EvidenceImage } from './EvidenceImage'
export function EvidenceDialog({ frame, onClose }: { frame: Evidence; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    dialog?.showModal()
    return () => {
      dialog?.close()
    }
  }, [])
  return (
    <dialog
      ref={ref}
      className="evidence-dialog"
      aria-labelledby="frame-title"
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="dialog-heading">
        <h2 id="frame-title">
          {t.evidence} <span className="timecode">{timecode(frame.timestamp_sec)}</span>
        </h2>
        <button className="icon-button" aria-label={t.close} onClick={onClose} autoFocus>
          <Icon name="close" />
        </button>
      </div>
      <EvidenceImage frame={frame} />
      <p>{t.originalEvidence}</p>
    </dialog>
  )
}
