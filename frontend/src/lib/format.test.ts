import { describe, expect, it } from 'vitest'
import { timecode, validateFile } from './format'
describe('video selection', () => {
  it('accepts MOV regardless of browser MIME', () => {
    expect(validateFile(new File(['mov'], 'camera.MOV', { type: '' }), 100)).toBeNull()
  })
  it('rejects unsupported, empty and oversized selections', () => {
    expect(validateFile(new File(['x'], 'file.txt'), 100)).toMatch(/Choose/)
    expect(validateFile(new File([], 'empty.mov'), 100)).toMatch(/empty/)
    expect(validateFile(new File(['1234'], 'large.mov'), 0.000001)).toMatch(/limit/)
  })
  it('formats actual timestamps', () => {
    expect(timecode(65.25)).toBe('01:05.2')
  })
})
