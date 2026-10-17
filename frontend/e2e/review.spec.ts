import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { job, status } from '../src/test/fixtures'
import { expectSettledVideo, prepareScreenshot } from './helpers'
let video: Buffer
let evidence: Buffer
test.beforeAll(() => {
  const directory = resolve('test-results', 'generated')
  mkdirSync(directory, { recursive: true })
  const movie = resolve(directory, `synthetic-${process.pid}.mp4`)
  const frame = resolve(directory, `synthetic-${process.pid}.jpg`)
  const portableRoot = resolve('..', '.tools', 'ffmpeg')
  const portable = existsSync(portableRoot)
    ? readdirSync(portableRoot)
        .map((folder) => resolve(portableRoot, folder, 'bin', 'ffmpeg.exe'))
        .find((file) => existsSync(file))
    : undefined
  const ffmpeg = process.env.FFMPEG_BINARY || portable || 'ffmpeg'
  execFileSync(
    ffmpeg,
    [
      '-hide_banner',
      '-loglevel',
      'error',
      '-y',
      '-f',
      'lavfi',
      '-i',
      'color=c=0xefe9ed:s=400x250:r=30:d=12',
      '-vf',
      'drawbox=x=100:y=70:w=80:h=80:color=0xFC9385:t=fill,drawbox=x=240:y=0:w=4:h=250:color=0xA31551:t=fill',
      '-an',
      '-c:v',
      'libx264',
      '-pix_fmt',
      'yuv420p',
      '-movflags',
      '+faststart',
      movie,
    ],
    { timeout: 30000, windowsHide: true },
  )
  execFileSync(
    ffmpeg,
    ['-hide_banner', '-loglevel', 'error', '-y', '-ss', '4', '-i', movie, '-frames:v', '1', frame],
    { timeout: 30000, windowsHide: true },
  )
  video = readFileSync(movie)
  evidence = readFileSync(frame)
})
test.beforeEach(async ({ page }) => {
  await page.route('**/api/ui/**', async (route) => {
    const url = new URL(route.request().url())
    const body = url.pathname.endsWith('/status')
      ? { ...status, ready: false, reasons: ['Configure a local detector and verified rules.'] }
      : url.pathname.endsWith('/session')
        ? { csrf_token: 'synthetic-test-token' }
        : url.pathname.endsWith('/rules')
          ? { rules: [] }
          : job
    await route.fulfill({ json: body })
  })
  await page.route('**/synthetic.mp4', (route) => {
    const range = route
      .request()
      .headers()
      .range?.match(/^bytes=(\d+)-(\d*)$/)
    const start = range ? Number(range[1]) : 0
    const end = range?.[2] ? Math.min(Number(range[2]), video.length - 1) : video.length - 1
    return route.fulfill({
      status: range ? 206 : 200,
      contentType: 'video/mp4',
      headers: {
        'Accept-Ranges': 'bytes',
        'Content-Length': String(end - start + 1),
        ...(range ? { 'Content-Range': `bytes ${start}-${end}/${video.length}` } : {}),
      },
      body: video.subarray(start, end + 1),
    })
  })
  await page.route('**/synthetic-*.jpg', (route) =>
    route.fulfill({ contentType: 'image/jpeg', body: evidence }),
  )
})
test('upload keyboard access, honest readiness and responsive layout', async ({
  page,
}, testInfo) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Review cashier activity' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Analyze video', exact: true })).toBeDisabled()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused()
  await page.getByRole('button', { name: 'Choose video' }).focus()
  await expect(page.getByRole('button', { name: 'Choose video' })).toBeFocused()
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy()
  await prepareScreenshot(page)
  await page.screenshot({ path: testInfo.outputPath('upload.png'), fullPage: true })
})
test('refresh recovery, independent simultaneous events, dialog keyboard and seeking', async ({
  page,
}, testInfo) => {
  await page.goto('/analysis/synthetic-job')
  await expect(
    page.getByRole('heading', { name: 'Signs of possible violations detected' }),
  ).toBeVisible()
  await page.reload()
  await expect(
    page.getByRole('heading', { name: 'Signs of possible violations detected' }),
  ).toBeVisible()
  await expect
    .poll(() => page.locator('video').evaluate((node: HTMLVideoElement) => node.readyState))
    .toBeGreaterThan(0)
  await page
    .getByRole('button', { name: 'Review event 2: Second simultaneous event at 00:04' })
    .click()
  await expect(page.getByRole('heading', { name: 'Second simultaneous event' })).toBeVisible()
  await expect(page.locator('.inspector-copy > div').first().locator('p')).toHaveText(
    job.result!.events[1].observation,
  )
  await expectSettledVideo(page, 4)
  await page.getByRole('button', { name: 'Enlarge evidence frame 00:04' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Close', exact: true })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await page
    .getByRole('button', { name: 'Event 1: Shape crosses boundary at 00:04', exact: true })
    .click()
  await expect(
    page.getByRole('heading', { name: 'Shape crosses boundary', exact: true }),
  ).toBeVisible()
  await expect(page.locator('.inspector-copy > div').first().locator('p')).toHaveText(
    job.result!.events[0].observation,
  )
  await expectSettledVideo(page, 4)
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy()
  await prepareScreenshot(page)
  await page.screenshot({ path: testInfo.outputPath('review.png'), fullPage: true })
})
