import { expect, test, type Page } from '@playwright/test';
import { tradingFixture } from './tradingFixture';

interface ApiState {
  authenticated: boolean;
  scannerTriggers: number;
  candidateRefreshes?: number;
  candidates?: unknown[];
  signals?: unknown[];
}

const statusFixture = {
  scanner_status: 'ONLINE',
  scanner_mode: 'shadow',
  heartbeat: '2026-09-13T01:30:37+07:00',
  scanned_coins_count: 150,
  active_signals_count: 0,
  top_risk_symbol: '',
  model_version: 'v2',
  model_id: 'frozen_test',
  telegram_connected: true,
  threshold: 0.25,
};

const telemetryFixture = {
  scanner_engine_status: 'ONLINE',
  last_scan_timestamp: '2026-09-13T01:30:37+07:00',
  next_scan_in_seconds: 240,
  poll_interval_minutes: 5,
  api_endpoint: 'Binance USD-M',
  average_api_latency_ms: 42,
  active_scan_mode: 'volatile',
  active_scan_modes: ['volatile'],
  scanned_pairs_count: 150,
  signals_triggered_count: 0,
  stablecoins_excluded_count: 8,
  runtime_state: { status: 'running' },
  model_id: 'frozen_test',
  cycle: 2,
  max_coins: 150,
  logs: [],
  telegram_dispatches: [],
};

const auditFixture = {
  report_available: true,
  report_generated_at: '2026-09-12T10:00:00Z',
  report_matches_current_model: true,
  model_name: 'frozen_test',
  horizon: '24h',
  target_drawdown: '-8%',
  mae_allowed: '+4%',
  sample_size: 25,
  total_alerts: 30,
  has_enough_data: true,
  metrics: {
    precision: 0.36,
    walk_forward_precision: 0.4,
    ci_95_lower: 0.31,
    ci_95_upper: 0.49,
    brier_score: 0.18,
    ece: 0.03,
  },
  precision_by_risk_level: {
    HIGH: { n_judged: 25, n_hit: 9, precision: 0.36 },
  },
  lead_time: {
    mean_hours: 2.5,
    median_hours: 2.2,
    min_hours: 0.5,
    max_hours: 8,
  },
  quality_gates: { precision_gate: true },
  validation_checks: {
    walk_forward_status: 'passed',
    leakage_test: 'passed',
    embargo_period: '24h',
    point_in_time_verified: true,
  },
};

async function mockApi(page: Page, state: ApiState) {
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    let body: unknown = {};
    let status = 200;

    if (
      !state.authenticated &&
      (pathname === '/api/ai/config' ||
        pathname === '/api/tracking-watchlist' ||
        (request.method() !== 'GET' &&
          !pathname.startsWith('/api/auth/') &&
          pathname !== '/api/tracking-usage'))
    ) {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Unauthorized', auth_required: true }),
      });
      return;
    }

    if (pathname === '/api/auth/status') {
      body = {
        auth_required: false,
        admin_auth_required: true,
        authenticated: state.authenticated,
        role: state.authenticated ? 'admin' : 'guest',
      };
    } else if (pathname === '/api/auth/verify') {
      const payload = request.postDataJSON() as { password?: string };
      state.authenticated = payload.password === 'smoke-password';
      body = state.authenticated ? { ok: true } : { error: 'invalid password' };
      if (!state.authenticated) {
        await route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify(body),
        });
        return;
      }
    } else if (pathname === '/api/status') {
      body = statusFixture;
    } else if (pathname === '/api/signals') {
      body = state.signals ?? [];
    } else if (pathname === '/api/candidates/compare') {
      body = null;
    } else if (pathname === '/api/candidates/refresh') {
      state.candidateRefreshes = (state.candidateRefreshes ?? 0) + 1;
      status = 202;
      body = { status: 'queued' };
    } else if (pathname === '/api/candidates') {
      body = (state.candidates ?? []).map((candidate) => ({
        ...(candidate as Record<string, unknown>),
        ...((state.candidateRefreshes ?? 0) > 0 ? { scan_time: '2026-09-13T01:35:37+07:00' } : {}),
      }));
    } else if (pathname === '/api/audit') {
      body = auditFixture;
    } else if (pathname === '/api/market') {
      body = null;
    } else if (pathname === '/api/watchlist') {
      body = { active_modes: ['volatile'], manual_watchlist: [], presets: [] };
    } else if (pathname === '/api/tracking-watchlist') {
      body = [];
    } else if (pathname === '/api/scanner/telemetry') {
      body = telemetryFixture;
    } else if (pathname === '/api/models') {
      body = {
        models: [],
        total: 0,
        current_scanner_model_id: 'frozen_test',
      };
    } else if (pathname === '/api/scanner/trigger') {
      state.scannerTriggers += 1;
      body = { ok: true, accepted: true };
    } else if (pathname === '/api/fibo-short/snapshot') {
      body = {
        status: 'ok',
        branch: 'fibo_trend_short',
        updated_at: '2026-11-01T06:28:05Z',
        scanned_symbols_count: 50,
        total_signals: 0,
        fired_count: 0,
        qualified_fired_count: 0,
        armed_count: 2,
        watching_count: 5,
        items: [],
      };
    } else if (pathname === '/api/fibo-short/paper-oos') {
      body = {
        health: { code: 'OBSERVING', severity: 'ok', headline: 'Paper OOS v1 Đang Quan Sát', detail: '12 tài khoản NAV 100', heartbeat_age_sec: 5, engine_lag_sec: 10, orders_allowed: false, live_signoff: 'NOT_GRANTED' },
        study: { version: 'paper_oos_v1', protocol_sha256: 'abc123', protocol_verified: true, start_utc: '2026-10-18T04:00:00Z', end_utc: '2028-10-16T00:00:00Z', engine_clock_utc: '2026-11-01T06:28:00Z', completed_full_weeks: 2, target_full_weeks: 104, remaining_full_weeks: 102, progress_pct: 1.9, membership_month: '2026-10', membership_count: 50, active_signal_universe_count: 50, pending_signals_count: 0, open_positions_count: 0, closed_trades_count: 0 },
        accounts: [],
      };
    } else if (pathname === '/api/fibo-short/backtest') {
      body = {
        status: 'ok',
        in_sample_window: { end_utc: '2025-12-31T23:59:59+00:00', oos_reserved_from_utc: '2026-01-01T00:00:00+00:00', oos_touched: false },
        overall: { total_trades: 790, win_rate_pct: 58.2, avg_net_return_pct: 1.2, total_net_return_pct: 26.19, profit_factor: 1.85, avg_r_multiple: 0.45, tp1_hit_rate_pct: 62.0, tp2_hit_rate_pct: 38.0, tp3_hit_rate_pct: 19.0, sl_hit_rate_pct: 31.0, avg_hold_hours: 22.4 },
      };
    } else if (pathname === '/api/execution/dashboard') {
      body = tradingFixture();
    } else if (pathname.startsWith('/api/coin/')) {
      body = pathname.endsWith('/deep-analysis')
        ? {}
        : {
            symbol: pathname.split('/')[3],
            current_price: 1.25,
            probability: 0.82,
            risk_level: 'CRITICAL',
            metrics: {},
            chart_data: [],
          };
    }

    await route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });
}

test('guest browses public dashboard without login, saves browser tracking, gates AI/Settings, and Admin login unlocks privileges', async ({ page }) => {
  const state: ApiState = { authenticated: false, scannerTriggers: 0 };
  await page.addInitScript(() => {
    localStorage.setItem('dao_vang_app_language', 'vi');
  });
  await mockApi(page, state);
  await page.goto('/');

  // Public dashboard opens immediately without blocking lock screen
  await expect(page.getByTestId('main-workspace')).toBeVisible();
  await expect(page.getByTestId('admin-login-trigger')).toBeVisible();
  await expect(page.getByTestId('admin-login-modal')).toHaveCount(0);

  // Guest personal tracking saves locally in browser without hitting 401 server route
  await page.getByTestId('open-tracking').click();
  await page.getByLabel('Coin muốn theo dõi').fill('SOL');
  await page.getByRole('button', { name: 'Thêm coin theo dõi' }).click();
  await expect(page.getByTestId('tracking-SOLUSDT')).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('dao_vang_guest_tracking_watchlist_v1') || ''))
    .toContain('SOLUSDT');

  // Live 10k / Execution tab opens Read-Only for Guest with Admin control gate
  await page.getByTestId('workspace-pillar-live').click();
  await expect(page.getByTestId('trading-dashboard')).toContainText('CHẾ ĐỘ KHÁCH · CHỈ XEM');
  await expect(page.getByTestId('execution-admin-login')).toBeVisible();

  // System Settings shows Admin Gate Card for Guest
  await page.getByTestId('workspace-system-menu').click();
  await page.getByTestId('workspace-tab-settings').click();
  await expect(page.getByTestId('settings-admin-gate')).toBeVisible();

  // Clicking Floating AI Assistant opens dismissible Admin Login Modal; signing in unlocks Admin
  await page.getByTestId('floating-ai-button').click();
  await expect(page.getByTestId('admin-login-modal')).toBeVisible();
  await page.getByTestId('login-password').fill('smoke-password');
  await page.getByTestId('login-submit').click();

  await expect.poll(() => state.authenticated).toBe(true);
  await expect(page.getByTestId('admin-role-badge')).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('dao_vang_authenticated')))
    .toBe('1');
  await expect
    .poll(() => page.evaluate(() => JSON.stringify(localStorage)))
    .not.toContain('smoke-password');
});

test('authenticated dashboard loads the release-critical API chain', async ({ page }) => {
  const state: ApiState = { authenticated: true, scannerTriggers: 0 };
  const requestedPaths = new Set<string>();
  page.on('request', (request) => {
    const pathname = new URL(request.url()).pathname;
    if (pathname.startsWith('/api/')) requestedPaths.add(pathname);
  });
  await mockApi(page, state);
  await page.goto('/');

  await expect(page.getByTestId('main-workspace')).toBeVisible();
  await expect(page.getByTestId('workspace-tab-decision')).toBeVisible();
  await expect.poll(() => requestedPaths.has('/api/status')).toBe(true);
  await expect.poll(() => requestedPaths.has('/api/scanner/telemetry')).toBe(true);
  await expect.poll(() => requestedPaths.has('/api/audit')).toBe(true);
});

test('scanner trigger and model audit report remain operable', async ({ page }) => {
  const state: ApiState = { authenticated: true, scannerTriggers: 0 };
  await page.addInitScript(() => {
    localStorage.setItem('peakpulse_dev_mode', 'true');
  });
  await mockApi(page, state);
  await page.goto('/');
  await expect(page.getByTestId('main-workspace')).toBeVisible();

  await page.getByTestId('workspace-system-menu').click();
  await page.getByTestId('workspace-tab-telemetry').click();
  await page.getByTestId('scanner-trigger').click();
  await expect.poll(() => state.scannerTriggers).toBe(1);
  await expect(page.getByText(/Đã ghi nhận yêu cầu quét|Scan requested/)).toBeVisible();

  await page.getByTestId('workspace-system-menu').click();
  await page.getByTestId('workspace-tab-audit').click();
  await expect(page.getByTestId('model-audit-report')).toBeVisible();
  await expect(page.getByTestId('model-audit-report')).toContainText('frozen_test');
  await expect(page.getByTestId('model-audit-report')).toContainText('36.0%');
});

test('V1 candidate actions, stale analysis, and refresh feedback remain operable', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('dao_vang_app_language', 'vi');
  });
  const candidateBase = {
    price: 1.25,
    score: 82.5,
    risk: 'CRITICAL',
    oi_24h: '+12.5%',
    funding: '+0.120%',
    taker_ratio: 0.68,
    volume_24h: '$12.0M',
    age: '2m ago',
    recommendation: 'HIGH_CONFIDENCE',
    calibrated_probability: 0.82,
    data_quality_score: 0.96,
    quality_status: 'valid',
    stage: 'DISTRIBUTION',
  };
  const state: ApiState = {
    authenticated: true,
    scannerTriggers: 0,
    candidateRefreshes: 0,
    candidates: [
      {
        ...candidateBase,
        symbol: 'TESTUSDT',
        scan_time: '2026-09-13T01:30:37+07:00',
        alertable: true,
        is_stale: false,
        market_cap_usd: 2_250_000_000,
        market_cap_str: '$2.3B',
        market_cap_tier: 'MID',
        market_cap_source: 'binance_agent_os',
        market_cap_is_estimate: false,
      },
      { ...candidateBase, symbol: 'OLDUSDT', scan_time: '2026-09-12T01:30:37+07:00', alertable: false, is_stale: true },
    ],
    signals: [{
      id: 'TESTUSDT-signal',
      symbol: 'TESTUSDT',
      name: 'TEST',
      probability: 0.82,
      risk_level: 'CRITICAL',
      two_tier_state: 'FIRED',
      signal_time: '2026-09-13T01:30:37+07:00',
      signal_price: 1.25,
      target_drawdown: -8,
      target_price: 1.15,
      validity_hours_left: 12,
      lead_time_avg_hours: 2,
      oi_change_24h: '+12.5%',
      taker_sell_ratio: 0.68,
      funding_rate: '+0.120%',
      rsi_divergence: true,
      trade_setup: { entry_price: 1.25, stop_loss: 1.3, tp1: 1.18, tp2: 1.12 },
    }],
  };
  const requestedPaths: string[] = [];
  page.on('request', request => requestedPaths.push(new URL(request.url()).pathname));
  await mockApi(page, state);
  await page.goto('/');

  await page.getByTestId('workspace-tab-ranking').click();
  await expect(page.getByTestId('candidate-ranking')).toBeVisible();
  await expect(page.getByText('V1 · Bản chính duy nhất')).toBeVisible();
  await expect(page.getByText('Dữ liệu 96% · 2m ago').first()).toBeVisible();
  await expect(page.getByTestId('candidate-market-cap-TESTUSDT')).toHaveText('⚡$2.3B');
  await expect(page.getByTestId('candidate-market-cap-OLDUSDT')).toHaveCount(0);
  expect(requestedPaths).not.toContain('/api/candidates/compare');

  await page.getByTestId('candidate-action-TESTUSDT').click();
  await expect(page.getByText('SHORT SETUP')).toBeVisible();
  await page.getByTestId('order-modal-close').click();

  await page.getByTestId('workspace-tab-ranking').click();
  await expect(page.getByTestId('candidate-action-OLDUSDT')).toBeEnabled();
  await expect(page.getByTestId('candidate-action-OLDUSDT')).toHaveText('Phân tích');

  await page.getByTestId('candidate-refresh').click();
  await expect.poll(() => state.candidateRefreshes).toBe(1);
  await expect(page.getByTestId('candidate-refresh-status')).toContainText('Đã cập nhật', { timeout: 10_000 });
  await expect(page.getByTestId('candidate-refresh')).toBeEnabled();
});

test('4 top-level pillars (Signals, Shadow Live, Live, System) switch cleanly across sub-tabs', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('dao_vang_app_language', 'vi');
  });
  const state: ApiState = { authenticated: true, scannerTriggers: 0 };
  await mockApi(page, state);
  await page.goto('/');

  // Pillar 1: Tín hiệu (Default landing on FIBO_SHORT, plus Phương pháp & Kiểm toán)
  await expect(page.getByTestId('workspace-pillar-signals')).toBeVisible();
  await expect(page.getByTestId('workspace-tab-fibo_short')).toBeVisible();
  await page.getByTestId('workspace-tab-models').click();
  await expect(page.getByText(/Phương Pháp 4 Nhân Tố/)).toBeVisible();

  // Pillar 2: Shadow Live (Paper OOS v1 + Đối chiếu Phiên bản)
  await page.getByTestId('workspace-pillar-shadow_live').click();
  await expect(page.getByTestId('workspace-tab-paper_oos')).toBeVisible();
  await expect(page.getByTestId('workspace-tab-shadow_compare')).toBeVisible();
  await page.getByTestId('workspace-tab-shadow_compare').click();

  // Pillar 3: Live (Real Binance Account ExecutionDashboard + Vị thế Theo dõi)
  await page.getByTestId('workspace-pillar-live').click();
  await expect(page.getByTestId('workspace-tab-live_account')).toBeVisible();
  await expect(page.getByTestId('trading-dashboard')).toBeVisible();
  await page.getByTestId('workspace-tab-watchlist').click();

  // Pillar 4: Hệ thống (Cài đặt + Hạ tầng & Trạng thái)
  await page.getByTestId('workspace-system-menu').click();
  await expect(page.getByTestId('workspace-tab-settings')).toBeVisible();
  await expect(page.getByTestId('workspace-tab-telemetry')).toBeVisible();
});

test('non-FIRED Fibo setup handoff renders ML probability as N/A without fabricating an actionable alert', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('dao_vang_app_language', 'vi');
  });
  const state: ApiState = { authenticated: true, scannerTriggers: 0 };
  await mockApi(page, state);
  await page.route('**/api/fibo-short/snapshot', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        branch: 'fibo_trend_short',
        updated_at: '2026-11-01T06:28:05Z',
        scanned_symbols_count: 50,
        total_signals: 1,
        fired_count: 0,
        qualified_fired_count: 0,
        armed_count: 1,
        watching_count: 0,
        items: [
          {
            id: 'fibo_sol_armed',
            symbol: 'SOLUSDT',
            higher_timeframe: '4h',
            confirm_timeframe: '1h',
            stage: 'ARMED_IN_FIBO_ZONE',
            score: 64,
            conviction_tier: 'B',
            signal_time: '2026-11-01T06:00:00Z',
            current_price: 142.5,
            wave: {
              symbol: 'SOLUSDT',
              timeframe: '4h',
              prior_low_price: 90,
              prior_low_time: '2026-10-20T00:00:00Z',
              prior_pump_pct: 0.65,
              swing_high_price: 148.5,
              swing_high_time: '2026-10-29T00:00:00Z',
              reversal_candle_time: '2026-10-29T04:00:00Z',
              reversal_candle_open: 147,
              reversal_candle_close: 141,
              reversal_candle_bearish: true,
              impulse_low_price: 134,
              impulse_low_time: '2026-10-31T00:00:00Z',
              impulse_drop_pct: 0.097,
              bars_since_swing_high: 18,
              bars_since_impulse_low: 6,
              wave_ker: 0.48,
              impulse_ker: 0.56,
              pst_pass: true,
            },
            fibo_levels: {
              level_1000: 148.5,
              level_0886: 146.85,
              level_0786: 145.4,
              level_0618: 142.96,
              level_0500: 141.25,
              level_0382: 139.54,
              level_0236: 137.42,
              level_0000: 134,
              ext_1272: 130.06,
              ext_1618: 125.04,
              wave_range: 14.5,
            },
            h1_confirmation: {
              candle_time: '2026-11-01T06:00:00Z',
              open: 141.8,
              high: 142.9,
              low: 141.5,
              close: 142.5,
              is_red_candle: false,
              no_gain_1h: false,
              price_ret_1h: 0.0049,
              touched_fibo_zone: true,
              max_pullback_fibo_ratio: 0.614,
              current_fibo_ratio: 0.586,
              cond1_bearish_pattern: false,
              pattern_name: 'NONE',
              pattern_name_vi: 'Chưa có',
              cond2_break_prev_low: false,
              break_description_vi: 'Chưa phá đáy H1',
              confirmed: false,
              confirmation_tier: 'UNCONFIRMED',
              reason_vi: 'Đang hồi trong vùng Fibo, chờ nến H1 đóng đỏ phá đáy.',
            },
            trade_setup: {
              entry_price: 142.5,
              entry_zone_low: 141.25,
              entry_zone_high: 142.96,
              entry_zone: '$141.25 - $142.96',
              stop_loss: 149.2,
              stop_loss_pct: 4.7,
              sl_m6: 147.2,
              sl_m6_pct: 3.3,
              tp1: 134.0,
              tp1_pct: 5.96,
              tp2: 130.06,
              tp2_pct: 8.73,
              tp3: 125.04,
              tp3_pct: 12.25,
              rr_ratio: 2.65,
              rr_tp1: 1.8,
              rr_tp2: 2.65,
              rr_tp3: 3.71,
              rr_m6_tp1: 1.8,
              rr_m6_tp2: 2.65,
              atr_1h: 1.4,
              sl_within_cap: true,
              recommended_notional_pct: 15.1,
            },
            matched_policies: [],
            primary_policy: 'watch_only',
            explanation_vi: ['Đang chờ xác nhận H1'],
          },
        ],
      }),
    });
  });
  await page.route('**/api/coin/SOLUSDT*', async (route) => {
    const p = new URL(route.request().url()).pathname;
    if (p.endsWith('/klines')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ klines: [] }) });
      return;
    }
    if (p.endsWith('/deep-analysis')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        symbol: 'SOLUSDT',
        name: 'Solana',
        current_price: 142.5,
        probability: null,
        risk_level: null,
        metrics: {},
        chart_data: [],
      }),
    });
  });

  await page.goto('/');
  await page.getByTestId('fibo-open-decision').click();

  const banner = page.getByTestId('fibo-provenance-banner');
  await expect(banner).toBeVisible();
  await expect(banner).toContainText('ARMED_IN_FIBO_ZONE');
  await expect(banner).toContainText('Chỉ xem biểu đồ, không tạo lệnh');
  await expect(banner).toContainText('N/A');

  // Ensure no fabricated 78% ML probability, FIRED state, or actionable trade setup card exists
  await expect(page.getByTestId('main-workspace')).not.toContainText('78.0%');
  await expect(page.getByTestId('main-workspace')).not.toContainText('78%');
  await expect(page.getByText('SHORT SETUP')).toHaveCount(0);
});
