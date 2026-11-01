import { expect, test, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

const coinDetail = {
  symbol: 'DOGEUSDT',
  name: 'Dogecoin',
  current_price: 0.21456,
  probability: 0.78,
  risk_level: 'HIGH',
  target_drawdown: 0.20,
  target_price: 0.17165,
  signal_timestamp: '2026-09-13T01:30:37+07:00',
  chart_source: 'api',
  chart_data: Array.from({ length: 24 }, (_, index) => ({
    time: 1_789_244_400 + index * 900,
    time_iso: new Date((1_789_244_400 + index * 900) * 1000).toISOString(),
    open: 0.21 + index * 0.0002,
    high: 0.213 + index * 0.0002,
    low: 0.208 + index * 0.0002,
    close: 0.211 + index * 0.0002,
    price: 0.211 + index * 0.0002,
    volume: 1_500_000 + index * 10_000,
  })),
  metrics: {
    oi_change_24h: '+18.4%',
    taker_sell_ratio: 0.61,
    funding_rate: '0.034%',
    funding_rate_source: 'binance',
    rsi_15m: 73.2,
    volume_delta_24h: '+122%',
  },
  attribution_method: 'none',
  feature_drivers: [],
};

async function mockDecisionApi(page: Page) {
  await page.route('**/api/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    let body: unknown = {};

    if (pathname === '/api/auth/status') body = { auth_required: true, authenticated: true };
    else if (pathname === '/api/status') body = { scanner_status: 'ONLINE', scanner_mode: 'volatile', model_id: 'v3.1', threshold: 0.7 };
    else if (pathname === '/api/signals') body = [];
    else if (pathname === '/api/candidates') body = [];
    else if (pathname === '/api/audit') body = null;
    else if (pathname === '/api/market') body = null;
    else if (pathname === '/api/watchlist') body = { active_modes: ['volatile'], manual_watchlist: [], presets: [] };
    else if (pathname === '/api/tracking-watchlist') body = [];
    else if (pathname === '/api/scanner/telemetry') body = { scanner_engine_status: 'ONLINE', active_scan_modes: ['volatile'], logs: [], telegram_dispatches: [] };
    else if (pathname === '/api/models') body = { models: [], total: 0, current_scanner_model_id: 'v3.1' };
    else if (pathname === '/api/coin/DOGEUSDT') body = coinDetail;
    else if (pathname === '/api/coin/DOGEUSDT/deep-analysis') body = { symbol: 'DOGEUSDT', calibrated_probability: 0.78, recommendation: 'SHORT_CANDIDATE' };
    else if (pathname === '/api/coin/DOGEUSDT/chart') body = { klines: coinDetail.chart_data };

    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
}

test('mobile decision and CTA stay above the fixed navigation without overlap', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    localStorage.setItem('dao_vang_app_language', 'vi');
  });
  await mockDecisionApi(page);
  await page.goto('/#coin=DOGEUSDT');

  await expect(page.getByTestId('main-workspace')).toBeVisible();
  await page.getByTestId('workspace-tab-decision').click();

  const nav = page.getByTestId('mobile-bottom-nav');
  const actions = page.getByTestId('mobile-sticky-actions');
  const assistant = page.getByTestId('floating-ai-button');
  const decision = page.getByTestId('decision-summary-column');
  const chart = page.getByTestId('decision-chart-column');
  const primaryCta = actions.getByRole('button', { name: /Vào Lệnh Short/i });

  await expect(page.getByText('Quyết định hiện tại')).toBeVisible();
  await expect(primaryCta).toBeVisible();
  await expect(decision).toBeVisible();
  await expect(chart).toBeVisible();

  const geometry = await page.evaluate(() => {
    const rect = (testId: string) => {
      const element = document.querySelector<HTMLElement>(`[data-testid="${testId}"]`);
      if (!element) throw new Error(`Missing ${testId}`);
      const box = element.getBoundingClientRect();
      return { top: box.top, right: box.right, bottom: box.bottom, left: box.left };
    };
    const main = document.querySelector('main');
    return {
      viewportHeight: window.innerHeight,
      viewportWidth: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      mainPaddingBottom: main ? Number.parseFloat(getComputedStyle(main).paddingBottom) : 0,
      nav: rect('mobile-bottom-nav'),
      actions: rect('mobile-sticky-actions'),
      assistant: rect('floating-ai-button'),
      decision: rect('decision-summary-column'),
      chart: rect('decision-chart-column'),
    };
  });

  expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.viewportWidth);
  expect(geometry.actions.bottom).toBeLessThanOrEqual(geometry.nav.top + 1);
  expect(geometry.assistant.bottom).toBeLessThanOrEqual(geometry.actions.top - 8);
  expect(geometry.mainPaddingBottom).toBeGreaterThanOrEqual(128);
  expect(geometry.chart.top).toBeLessThan(geometry.decision.top);
  expect((await primaryCta.boundingBox())!.y).toBeLessThan(geometry.viewportHeight);

  const artifactDir = path.resolve(process.cwd(), '..', 'artifacts', 'mobile-ux-brand-fix-20260913');
  mkdirSync(artifactDir, { recursive: true });
  await page.screenshot({ path: path.join(artifactDir, 'mobile-390x844.png'), fullPage: false });
});

test('desktop keeps the side-by-side decision layout without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await mockDecisionApi(page);
  await page.goto('/#coin=DOGEUSDT');

  const decision = page.getByTestId('decision-summary-column');
  const chart = page.getByTestId('decision-chart-column');
  await expect(decision).toBeVisible();
  await expect(chart).toBeVisible();

  const decisionBox = (await decision.boundingBox())!;
  const chartBox = (await chart.boundingBox())!;
  expect(chartBox.x).toBeLessThan(decisionBox.x);
  expect(Math.abs(chartBox.y - decisionBox.y)).toBeLessThan(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1440);

  const artifactDir = path.resolve(process.cwd(), '..', 'artifacts', 'mobile-ux-brand-fix-20260913');
  mkdirSync(artifactDir, { recursive: true });
  await page.screenshot({ path: path.join(artifactDir, 'desktop-1440x1000.png'), fullPage: false });
});
