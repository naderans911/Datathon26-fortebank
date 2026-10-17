import { expect, test } from '@playwright/test'
import { expectSettledVideo, prepareScreenshot } from './helpers'

test('local synthetic annotations preserve points, allow multiple events and recover on refresh', async ({
  page,
}, testInfo) => {
  await page.goto('/review')
  await expect(page.getByRole('heading', { name: 'Review matched training videos' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Jump to supplied point' })).toBeEnabled()
  await expectSettledVideo(page, 4)
  await page.getByRole('button', { name: 'Play 5 seconds before the point' }).click()
  await expect
    .poll(() => page.locator('video').evaluate((video: HTMLVideoElement) => video.currentTime))
    .toBeGreaterThan(0.2)
  await page.locator('video').evaluate((video: HTMLVideoElement) => video.pause())
  await page.getByRole('button', { name: 'Jump to supplied point' }).click()
  await expectSettledVideo(page, 4)
  // Each viewport starts from a fresh empty annotation in this synthetic-only fixture.
  while (await page.getByRole('button', { name: /^Remove event/ }).count()) {
    await page
      .getByRole('button', { name: /^Remove event/ })
      .first()
      .click()
  }
  await page.getByRole('button', { name: 'Add event', exact: true }).click()
  await page.getByRole('button', { name: 'Add event', exact: true }).click()
  await expect(page.getByLabel('Start time (seconds, optional)').first()).toHaveValue('')
  await expect(page.getByLabel('End time (seconds, optional)').first()).toHaveValue('')
  await expect(page.getByLabel('Event type / category').first()).toHaveValue('')
  await page
    .getByLabel('Visible observation')
    .first()
    .fill('A generated magenta square is visible.')
  await page
    .getByLabel('Visible observation')
    .nth(1)
    .fill('A generated sky-blue square is visible.')
  await page.getByLabel('Start time (seconds, optional)').nth(1).fill('3.5')
  await page.getByLabel('End time (seconds, optional)').nth(1).fill('5')
  await page.getByRole('button', { name: 'Save annotations locally' }).click()
  await expect(page.getByText('Annotations saved locally.')).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('Visible observation').first()).toHaveValue(
    'A generated magenta square is visible.',
  )
  await expect(page.getByLabel('Visible observation').nth(1)).toHaveValue(
    'A generated sky-blue square is visible.',
  )
  await expect(page.getByLabel('Start time (seconds, optional)').first()).toHaveValue('')
  await expect(page.getByLabel('End time (seconds, optional)').nth(1)).toHaveValue('5')
  await expectSettledVideo(page, 4)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await prepareScreenshot(page)
  await page.waitForTimeout(600)
  await page.screenshot({ path: testInfo.outputPath('local-annotations.png'), fullPage: true })
})
