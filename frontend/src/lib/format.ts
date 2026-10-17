import { t } from '../locales/en'
export function timecode(seconds: number) {
  const safe = Math.max(0, seconds || 0)
  return `${Math.floor(safe / 60)
    .toString()
    .padStart(2, '0')}:${Math.floor(safe % 60)
    .toString()
    .padStart(2, '0')}${safe % 1 ? `.${Math.floor((safe % 1) * 10)}` : ''}`
}
export function fileSize(bytes: number) {
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
export function validateFile(file: File, limitMb: number) {
  if (!/\.(mov|mp4|m4v|mkv)$/i.test(file.name)) return t.invalidType
  if (!file.size) return t.emptyFile
  if (file.size > limitMb * 1024 * 1024) return t.tooLarge(limitMb)
  return null
}
export function readable(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(readable).join('; ')
  if (typeof value === 'object')
    return Object.entries(value)
      .map(([k, v]) => `${k.replaceAll('_', ' ')}: ${readable(v)}`)
      .join(' · ')
  return String(value)
}
