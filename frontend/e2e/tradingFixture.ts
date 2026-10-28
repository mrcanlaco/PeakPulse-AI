export function tradingFixture() {
  const at = new Date().toISOString();
  return {
    environment: 'simulation', enabled: true, healthy: true, heartbeat_age_seconds: 1,
    account_fresh: true, account_age_seconds: 1, generated_at: at,
    config: { max_positions: 1 }, account: { at, wallet: 500, equity: 480, available: 475, unrealized: -20, peak: 500, drawdown: 0.04 },
    pause: { paused: false, reason: '' }, manifest_id: 'test', live_gate: { eligible: false, reasons: ['evidence_required'] },
    source_health: { healthy: true },
    equity_curve: [500, 502, 501, 497, 488, 480].map((equity, i) => ({ at: new Date(Date.now()-(5-i)*3600000).toISOString(), equity, drawdown: Math.max(0, 1-equity/502) })),
    totals: { recorded_fees: 0.12, recorded_funding: -0.03, closed_count: 1, wins: 1, closed_net_pnl: 1.2, equity_change: -20, observed_since: at },
    progress: { manifest_loaded: true, observed_days: 12, independent_events: 42, time_windows: 2, required_days: 28, required_events: 100, required_windows: 3 },
    setup: { credentials_present: true, manifest_loaded: true, worker_enabled: true, account_observed: true },
    commands: [], activity: [], recent_signals: [{ event_id: 'one', symbol: 'ABCUSDT', at, eligible: true, decision: 'submitted', reasons: [] }],
    trade_history_truncated: false, unmanaged_positions: [],
    trades: [
      { id: 'trade1', symbol: 'ABCUSDT', status: 'open', created_at: at, entry_price: 100, remaining_qty: 0.249, target: 1, tp_price: 95.9, funding: -0.01, unrealized: -20, mark_price: 180.32, tp_status: 'NEW', last_reconciled_at: at },
      { id: 'trade2', symbol: 'XYZUSDT', status: 'closed', created_at: at, closed_at: at, entry_price: 100, target: 1.2, net_pnl: 1.2, funding: -0.02 },
    ],
  };
}
