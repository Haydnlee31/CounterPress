const { chromium } = require('playwright')
const assert = require('node:assert/strict')
;(async () => {
  const browser = await chromium.launch({
    ...(process.env.CHROME_EXECUTABLE
      ? { executablePath: process.env.CHROME_EXECUTABLE }
      : {}),
    headless: true,
  })
  try {
    const context = await browser.newContext({
      viewport: { width: 1365, height: 1000 },
      reducedMotion: 'reduce',
    })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    const base = process.argv[2] || 'http://127.0.0.1:8010'
    await page.goto(base)
    await page.getByLabel('1 to 4', { exact: true }).waitFor()
    assert.equal(
      await page.getByLabel('Local viewer', { exact: true }).count(),
      0,
    )
    await page.screenshot({
      path: 'docs/screenshots/matchday-desktop.png',
      fullPage: true,
    })
    await page.getByRole('button', { name: /Catch me up/ }).click()
    await page
      .getByRole('region', { name: 'The story in a few moments' })
      .waitFor()
    await page
      .getByRole('button', { name: 'Show the moments', exact: true })
      .click()
    await page.getByRole('region', { name: 'See it for yourself' }).waitFor()
    assert((await page.getByRole('button', { name: /Rory Ellis/ }).count()) > 0)
    await page.getByRole('button', { name: /Neutral · choose a side/ }).click()
    await page
      .getByLabel('Follow a team', { exact: true })
      .selectOption('northport')
    await page.getByLabel('Language', { exact: true }).selectOption('zh-Hans')
    await page.getByRole('region', { name: '几个事件，了解故事' }).waitFor()
    await page.locator('.fan-hero').waitFor()
    assert(
      (
        await page
          .getByRole('region', { name: '几个事件，了解故事' })
          .innerText()
      ).includes('4 次'),
    )
    await page.reload()
    await page.locator('.fan-hero').waitFor()
    assert.equal(
      await page.getByLabel('Language', { exact: true }).inputValue(),
      'zh-Hans',
    )
    await page.getByRole('button', { name: /Northport/ }).click()
    assert.equal(
      await page.getByLabel('Follow a team', { exact: true }).inputValue(),
      'northport',
    )
    await page.getByRole('button', { name: '清除偏好', exact: true }).click()
    await page.getByRole('button', { name: 'Done', exact: true }).click()
    for (const scenario of [
      'pressure-increase',
      'progression-increase',
      'contribution-increase',
    ]) {
      await page
        .getByLabel('Explore a story', { exact: true })
        .selectOption(scenario)
      await page.locator('.fan-hero').waitFor()
      await page
        .getByRole('button', { name: 'Show the moments', exact: true })
        .click()
      await page.getByRole('region', { name: 'See it for yourself' }).waitFor()
    }
    await page
      .getByLabel('Explore a story', { exact: true })
      .selectOption('increase')
    await page.getByLabel('1 to 4', { exact: true }).waitFor()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.screenshot({
      path: 'docs/screenshots/matchday-mobile.png',
      fullPage: true,
    })
    for (const width of [360, 390, 640, 1365]) {
      await page.setViewportSize({ width, height: 900 })
      assert(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `Horizontal overflow at ${width}`,
      )
    }
    await page.setViewportSize({ width: 640, height: 900 })
    await page.evaluate(
      () => (document.documentElement.style.fontSize = '200%'),
    )
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      '200% text-size overflow',
    )
    await page
      .getByRole('button', { name: 'Explore replay', exact: false })
      .click()
    await page
      .getByRole('button', { name: 'Back to 48:00', exact: true })
      .click()
    await page
      .getByRole('heading', { name: 'The comparison is still unfolding.' })
      .waitFor()
    assert.equal(await page.getByLabel('1 to 4', { exact: true }).count(), 0)
    await page.evaluate(() => (document.documentElement.style.fontSize = ''))
    if (process.env.COUNTERPRESS_CHECK_CORRECTIONS === '1') {
      await page
        .getByLabel('Explore a story', { exact: true })
        .selectOption('stream-recovery')
      await page.getByLabel('1 to 4', { exact: true }).waitFor()
      const timeline = page.getByLabel('Match time', { exact: true })
      await timeline.focus()
      await timeline.press('End')
      await page.getByLabel('1 to 2', { exact: true }).waitFor()
      for (let i = 0; i < 5; i++) await timeline.press('ArrowLeft')
      await page
        .getByText(
          'An earlier story was withdrawn because the revised events no longer support it. Other supported stories are shown below.',
          { exact: true },
        )
        .waitFor()
      assert.equal(await page.getByLabel('1 to 2', { exact: true }).count(), 0)
      for (let i = 0; i < 5; i++) await timeline.press('ArrowLeft')
      await page.getByLabel('1 to 3', { exact: true }).waitFor()
      for (let i = 0; i < 5; i++) await timeline.press('ArrowLeft')
      await page.getByLabel('1 to 4', { exact: true }).waitFor()
    }
    await page.getByRole('link', { name: 'Explore data', exact: true }).click()
    await page.getByLabel('Local viewer', { exact: true }).waitFor()
    assert.deepEqual(errors, [])
    if (process.env.COUNTERPRESS_CHECK_CORRECTIONS === '1')
      console.log('PASS: historical recovery 4/3/withdrawn/2')
    console.log(
      'PASS: actual HTTP fan view, inline evidence, persistent bilingual preferences, all four story families, mobile widths, rewind and analysis navigation',
    )
  } finally {
    await browser.close()
  }
})().catch((e) => {
  console.error(e.message)
  process.exit(1)
})
