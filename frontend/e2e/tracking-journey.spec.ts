import { test, expect, type Page } from '@playwright/test';
import type { TrackingWatchlistItem } from '../src/types';

async function setup(page: Page) {
  const now = new Date().toISOString();
  let items: TrackingWatchlistItem[] = [];
  await page.addInitScript(() => localStorage.setItem('dao_vang_app_language', 'vi'));
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    let body: unknown = {};
    if (path === '/api/auth/status') body = { authenticated: true, auth_required: true };
    else if (path === '/api/status') body = { scanner_status: 'ONLINE', active_signals_count: 0, threshold: .25 };
    else if (path === '/api/signals' || path === '/api/candidates') body = [];
    else if (path === '/api/market' || path === '/api/audit' || path === '/api/scanner/telemetry') body = null;
    else if (path === '/api/models') body = { models: [] };
    else if (path === '/api/watchlist') body = { active_scan_modes: ['volatile'], manual_watchlist: [], presets: [] };
    else if (path === '/api/tracking-usage') body = { visitors_7d: 3, returning_visitors_7d: 1 };
    else if (path === '/api/tracking-watchlist' && method === 'POST') {
      const data = route.request().postDataJSON();
      items = [{ id: 'test', symbol: `${data.symbol.replace(/USDT$/, '')}USDT`, source: 'manual', status: 'WATCHING', signal_status: 'NO_SIGNAL', source_price: 100, current_price: 95, source_price_time: now, source_price_evidence: 'binance_closed_5m', market_data_status: 'FRESH', created_at: now, updated_at: now, source_reason: 'Theo dõi biến động giá', checkpoints: { '24': { status: 'READY', return_pct: -5, max_drop_pct: 8, max_rise_pct: 3, at: now }, '48': { status: 'MISSING', reason: 'price_gaps' } }, notifications: [{ id: 'n', at: now, code: 'PRICE_MOVE', message: 'Giá thay đổi -5.0%', read: false }], history: [{ at: now, event: 'SAVED', changes: {} }] }];
      body = { item: items[0] };
    } else if (path === '/api/tracking-watchlist') body = items;
    else if (path === '/api/tracking-watchlist/test' && method === 'PATCH') {
      const patch = route.request().postDataJSON();
      items[0] = { ...items[0], ...patch };
      if (patch.read_notifications) items[0].notifications?.forEach(n => n.read = true);
      body = { item: items[0] };
    } else if (path === '/api/tracking-watchlist/test' && method === 'DELETE') {
      items[0] = { ...items[0], status: 'CLOSED', archived_at: now };
      body = { status: 'removed' };
    } else if (path === '/api/tracking-watchlist/test/paper') {
      const action = route.request().postDataJSON().action;
      items[0].paper_trade = action === 'open'
        ? { status: 'OPEN', side: 'SHORT', notional: 1000, quantity: 10, entry_price: 100, entry_fee: .5, fee_bps: 5, slippage_bps: 5, opened_at: now, funding: { status: 'PENDING', cashflow: null } }
        : { ...items[0].paper_trade!, status: 'CLOSED', exit_price: 95, closed_at: now, gross_pnl: 50, fees: 1, funding: { status: 'VERIFIED', cashflow: -2, settlements: 1 }, net_pnl: 47 };
      body = { item: items[0] };
    }
    await route.fulfill({ json: body });
  });
}

for (const width of [390, 1440]) {
  test(`new user follows a coin, reviews evidence, simulates and retains history at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await setup(page);
    await page.goto('/');
    const quick = page.getByTestId('open-tracking');
    if (width >= 640) {
      await quick.click();
    } else {
      await page.getByTestId('mobile-bottom-nav').getByRole('button', { name: /^Live$/i }).click();
      await page.getByTestId('workspace-tab-watchlist').click();
    }
    await page.getByLabel('Coin muốn theo dõi').fill('BTC');
    await page.getByRole('button', { name: 'Thêm coin theo dõi' }).click();
    const card = page.getByTestId('tracking-BTCUSDT');
    await expect(card).toBeVisible();
    await expect(card.getByTestId('checkpoint-24')).toContainText('-5.00%');
    await expect(card.getByTestId('checkpoint-48')).toContainText('Chưa đủ dữ liệu');
    await card.getByRole('button', { name: 'Hữu ích', exact: true }).click();
    await expect(card.getByRole('button', { name: 'Hữu ích', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await card.getByRole('button', { name: 'Đánh dấu đã đọc' }).click();
    await expect(card.getByRole('button', { name: 'Đánh dấu đã đọc' })).toHaveCount(0);
    await card.getByText('Thử bằng vốn giả lập', { exact: true }).click();
    await card.getByRole('button', { name: 'Mở giả lập', exact: true }).click();
    await expect(card.getByText('Đóng giả lập theo giá mới', { exact: true })).toBeVisible();
    await card.getByRole('button', { name: 'Đóng giả lập theo giá mới' }).click();
    await expect(card.getByText('Lãi/lỗ ròng giả lập: 47.00 USDT')).toBeVisible();
    await page.screenshot({ path: `test-results/tracking-${width}.png`, fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    await card.getByRole('button', { name: /Bỏ theo dõi/i }).click();
    await expect(card).toHaveCount(0);
    await page.getByRole('button', { name: 'Toàn bộ lịch sử', exact: true }).click();
    await expect(card).toBeVisible();
    await page.reload();
    if (width >= 640) {
      await quick.click();
    } else {
      await page.getByTestId('mobile-bottom-nav').getByRole('button', { name: /^Live$/i }).click();
      await page.getByTestId('workspace-tab-watchlist').click();
    }
    await page.getByRole('button', { name: 'Toàn bộ lịch sử', exact: true }).click();
    await expect(card).toBeVisible();
  });
}
