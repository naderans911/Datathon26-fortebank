import { test, expect } from '@playwright/test'
import type { Job } from '../src/lib/types'
import { expectSettledVideo, prepareScreenshot } from './helpers'

// Opt in against a locally running API with ENABLE_DEMO=true. No competition footage is used.
const liveApi = process.env.LIVE_API_URL
test('connected synthetic demo, protected media and honest failure states', async ({
  page,
}, testInfo) => {
  test.skip(!liveApi, 'Set LIVE_API_URL to a local running API with ENABLE_DEMO=true.')
  const jobs: string[] = []
  await page.goto(`${liveApi}/demo`)
  await expect(
    page.getByText('Demo — synthetic data; not a real compliance analysis'),
  ).toBeVisible()
  const variants = [
    ['positive', 'Positive example', 'Signs of possible violations detected'],
    ['negative', 'Negative example', 'No violation detected'],
    ['failed', 'Failed example', 'Analysis could not be completed'],
  ] as const
  try {
    for (const [kind, label, heading] of variants) {
      const responsePromise = page.waitForResponse((response) =>
        response.url().endsWith(`/api/ui/demo/${kind}`),
      )
      await page.getByRole('button', { name: label, exact: true }).click()
      const response = await responsePromise
      expect(response.ok()).toBeTruthy()
      const payload: Job = await response.json()
      jobs.push(payload.job_id)
      await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
      if (kind === 'positive') {
        await expect
          .poll(() => page.locator('video').evaluate((node: HTMLVideoElement) => node.readyState))
          .toBeGreaterThan(0)
        await page.getByRole('button', { name: /^Review event 2:/ }).click()
        const secondEvent = [...payload.result!.events].sort(
          (a, b) => a.timecode_sec - b.timecode_sec || a.id.localeCompare(b.id),
        )[1]
        await expect(page.locator('.inspector-copy > div').first().locator('p')).toHaveText(
          secondEvent.observation,
        )
        await expect(page.locator('.event-item.selected p')).toHaveText(secondEvent.observation)
        await expectSettledVideo(page, secondEvent.timecode_sec)
        await page.locator('video').evaluate((node: HTMLVideoElement) => node.play())
        await expect
          .poll(() => page.locator('video').evaluate((node: HTMLVideoElement) => node.currentTime))
          .toBeGreaterThan(secondEvent.timecode_sec + 0.2)
        await page.locator('video').evaluate((node: HTMLVideoElement) => node.pause())
        await page.getByRole('button', { name: /^Review event 2:/ }).click()
        await expectSettledVideo(page, secondEvent.timecode_sec)
        await expect
          .poll(() =>
            page
              .locator('.evidence-thumb img')
              .first()
              .evaluate((node: HTMLImageElement) => node.naturalWidth),
          )
          .toBeGreaterThan(0)
        expect(
          await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
        ).toBeTruthy()
        await prepareScreenshot(page)
        // Chromium's native media indicator fades after decoded playback/seek settles.
        await page.waitForTimeout(600)
        await page.screenshot({
          path: testInfo.outputPath('connected-positive.png'),
          fullPage: true,
        })
      } else if (kind === 'negative') {
        await expect(page.getByText(/not proof of complete compliance/)).toBeVisible()
      } else {
        await expect(
          page.getByRole('heading', { name: 'No violation detected', exact: true }),
        ).toHaveCount(0)
      }
    }
  } finally {
    const session = await page.request.get(`${liveApi}/api/ui/session`)
    const { csrf_token } = await session.json()
    for (const id of jobs) {
      const deleted = await page.request.delete(`${liveApi}/api/ui/jobs/${id}`, {
        headers: { 'X-CSRF-Token': csrf_token, Origin: liveApi! },
      })
      expect(deleted.status()).toBe(204)
    }
  }
})
