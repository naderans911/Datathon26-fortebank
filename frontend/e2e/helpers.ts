import { expect, type Page } from '@playwright/test'

export async function expectSettledVideo(page: Page, seconds: number) {
  await expect
    .poll(() => page.locator('video').evaluate((node: HTMLVideoElement) => node.currentTime))
    .toBeCloseTo(seconds, 1)
  await expect
    .poll(() =>
      page
        .locator('video')
        .evaluate((node: HTMLVideoElement) => node.readyState >= 3 && !node.seeking),
    )
    .toBeTruthy()
}

export async function prepareScreenshot(page: Page) {
  await page.evaluate(() => {
    ;(document.activeElement as HTMLElement | null)?.blur()
    window.scrollTo({ top: 0, behavior: 'instant' })
  })
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())))
}
