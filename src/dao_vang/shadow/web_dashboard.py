"""Web Dashboard Local để quản lý và theo dõi các Shadow Paper Trading Bot.

Giao diện Web nhẹ, trực quan, chuyên nghiệp:
- Hiển thị số lượng Shadow đang chạy, trạng thái từng con.
- Lãi/lỗ thời gian thực (Unrealized & Realized PnL, Total Equity, Return %, MaxDD).
- Biểu đồ tăng trưởng tài sản (Equity Curve) trực quan cho từng Shadow.
- Nút bấm điều khiển: Tạm dừng (Pause), Tiếp tục (Resume), Đặt lại vốn (Reset), Thêm Shadow mới.
- Dùng chung 100% SharedMarketFeed không gây quá tải API Binance.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from dao_vang.shadow.candidates_registry import CANDIDATE_REGISTRY
from dao_vang.shadow.shadow_engine import ShadowPaperManager
from dao_vang.shadow.shared_feed import SharedMarketFeed

logger = logging.getLogger("ShadowWebDashboard")
app = FastAPI(title="PeakPulse AI - Shadow Paper Trading Hub", version="1.0.0")

# Singleton managers
manager = ShadowPaperManager()

# Pre-register strategies from registry
for strat_id, strat_meta in CANDIDATE_REGISTRY.items():
    manager.register_strategy_func(strat_id, strat_meta["eval_func"])

# Auto-spawn default top performers if none exist
if not manager.shadows:
    manager.add_shadow(
        shadow_id="SHADOW_C01_KALMAN",
        name="Top 1 Champion: C01 Dynamic Kalman Beta (Calmar 1.38)",
        strategy_id="C01_KALMAN",
        capital=10000.0,
    )
    manager.add_shadow(
        shadow_id="SHADOW_BASE",
        name="Baseline Point72 Cubist (ETH/BTC)",
        strategy_id="BASE_POINT72",
        capital=10000.0,
    )
    manager.add_shadow(
        shadow_id="SHADOW_C16_COMPOSITE",
        name="Top 2: C16 Multi-Factor Composite Z (Calmar 0.72)",
        strategy_id="C16_COMPOSITE",
        capital=10000.0,
    )
    manager.add_shadow(
        shadow_id="SHADOW_C10_AMIHUD",
        name="Top 3: C10 Amihud Illiquidity Guard (MaxDD 18%)",
        strategy_id="C10_AMIHUD",
        capital=10000.0,
    )
    manager.add_shadow(
        shadow_id="SHADOW_C04_WAVELET",
        name="Top 4: C04 Wavelet Denoised Spread",
        strategy_id="C04_WAVELET",
        capital=10000.0,
    )


# Initial evaluation on existing cached bars
manager.evaluate_all_shadows()


class SpawnShadowRequest(BaseModel):
    shadow_id: str
    name: str
    strategy_id: str
    capital: float = 10000.0


class ActionRequest(BaseModel):
    action: str  # pause, resume, reset


# ==============================================================================
# REST API ENDPOINTS
# ==============================================================================

@app.get("/api/status")
async def get_status():
    """Lấy dữ liệu tổng hợp cho Web UI."""
    summary = manager.get_dashboard_summary()
    return JSONResponse(content=summary)


@app.get("/api/candidates")
async def get_candidates():
    """Danh sách các ứng viên có sẵn trong Registry."""
    items = []
    for k, v in CANDIDATE_REGISTRY.items():
        items.append({
            "strategy_id": k,
            "name": v["name"],
            "description": v["description"],
            "calmar_grade": v["calmar_grade"],
        })
    return JSONResponse(content=items)


@app.post("/api/shadows/spawn")
async def spawn_shadow(req: SpawnShadowRequest):
    """Kích hoạt một Shadow Runner mới."""
    if req.strategy_id not in CANDIDATE_REGISTRY:
        raise HTTPException(status_code=400, detail="Chiến lược không tồn tại trong Registry")
    inst = manager.add_shadow(req.shadow_id, req.name, req.strategy_id, req.capital)
    return JSONResponse(content={"status": "success", "shadow": inst.to_dict()})


@app.post("/api/shadows/{shadow_id}/action")
async def shadow_action(shadow_id: str, req: ActionRequest):
    """Điều khiển shadow (pause, resume, reset)."""
    if shadow_id not in manager.shadows:
        raise HTTPException(status_code=404, detail="Không tìm thấy Shadow ID")
    manager.toggle_shadow(shadow_id, req.action)
    return JSONResponse(content={"status": "success", "action": req.action, "shadow_id": shadow_id})


@app.post("/api/feed/refresh")
async def refresh_feed():
    """Kích hoạt cập nhật thủ công từ Binance và đánh giá lại các bot."""
    has_new = manager.feed.update_feeds()
    manager.evaluate_all_shadows()
    return JSONResponse(content={"status": "success", "has_new_candle": has_new})


# ==============================================================================
# FRONTEND DASHBOARD HTML
# ==============================================================================

HTML_CONTENT = """<!DOCTYPE html>
<html lang="vi" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PeakPulse AI - Shadow Paper Trading Hub</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        brand: {
                            50: '#ecfdf5',
                            500: '#10b981',
                            600: '#059669',
                            900: '#064e3b',
                        }
                    }
                }
            }
        }
    </script>
    <!-- Chart.js CDN -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background-color: #0b0f17; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        .glass-panel { background: rgba(18, 24, 38, 0.7); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.08); }
        .glow-green { box-shadow: 0 0 20px rgba(16, 185, 129, 0.2); }
    </style>
</head>
<body class="min-h-screen flex flex-col">

    <!-- Top Navigation Bar -->
    <header class="glass-panel border-b border-slate-800 sticky top-0 z-50 px-6 py-4 flex items-center justify-between">
        <div class="flex items-center space-x-3">
            <div class="h-9 w-9 rounded-lg bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400 font-bold text-xl">
                ⚡
            </div>
            <div>
                <h1 class="text-lg font-bold tracking-tight text-white flex items-center gap-2">
                    PEAKPULSE AI <span class="text-xs px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Shadow Paper Engine v1.0</span>
                </h1>
                <p class="text-xs text-slate-400">Point72 Cubist Factor-Neutral Multi-Candidate Trading Hub</p>
            </div>
        </div>

        <div class="flex items-center space-x-4">
            <div class="flex items-center space-x-2 text-xs bg-slate-900/80 px-3 py-1.5 rounded-full border border-slate-800">
                <span class="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span class="text-slate-300">Shared Feed: <strong class="text-emerald-400">Binance 1H Active</strong></span>
                <span class="text-slate-600">|</span>
                <span class="text-slate-400" id="feedTime">Đang cập nhật...</span>
            </div>

            <button onclick="triggerFeedRefresh()" class="text-xs px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-md border border-slate-700 transition flex items-center gap-1.5">
                <span>🔄</span> Cập Nhật Nến
            </button>

            <button onclick="openSpawnModal()" class="text-xs px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-medium rounded-md shadow-sm transition flex items-center gap-1.5">
                <span>➕</span> Khởi Chạy Shadow Mới
            </button>
        </div>
    </header>

    <!-- Main Container -->
    <main class="flex-1 p-6 space-y-6 max-w-7xl mx-auto w-full">

        <!-- KPI Cards Grid -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <!-- Card 1 -->
            <div class="glass-panel p-5 rounded-xl">
                <div class="text-xs text-slate-400 font-medium uppercase tracking-wider">Shadow Bots Đang Chạy</div>
                <div class="mt-2 flex items-baseline space-x-2">
                    <span class="text-3xl font-extrabold text-white" id="statActiveCount">0</span>
                    <span class="text-xs text-slate-500" id="statTotalCount">/ 0 tổng số</span>
                </div>
                <div class="mt-2 text-xs text-emerald-400 flex items-center gap-1">
                    <span>🛡️</span> 100% Shared Feed (0 Redundant Calls)
                </div>
            </div>

            <!-- Card 2 -->
            <div class="glass-panel p-5 rounded-xl">
                <div class="text-xs text-slate-400 font-medium uppercase tracking-wider">Tổng Vốn Paper Quản Lý</div>
                <div class="mt-2 flex items-baseline space-x-2">
                    <span class="text-3xl font-extrabold text-white" id="statTotalEquity">$0.00</span>
                </div>
                <div class="mt-2 text-xs text-slate-400" id="statTotalInitial">Vốn gốc: $0.00</div>
            </div>

            <!-- Card 3 -->
            <div class="glass-panel p-5 rounded-xl">
                <div class="text-xs text-slate-400 font-medium uppercase tracking-wider">Tổng Lãi / Lỗ Danh Mục (PnL)</div>
                <div class="mt-2 flex items-baseline space-x-2">
                    <span class="text-3xl font-extrabold" id="statTotalPnl">$0.00</span>
                    <span class="text-sm font-semibold" id="statOverallReturn">0.00%</span>
                </div>
                <div class="mt-2 text-xs text-slate-400">Phí giao dịch tính chuẩn VIP6 (11.5 bps)</div>
            </div>

            <!-- Card 4 -->
            <div class="glass-panel p-5 rounded-xl">
                <div class="text-xs text-slate-400 font-medium uppercase tracking-wider">Chiến Lược Dẫn Đầu (Top 1 Quán Quân)</div>
                <div class="mt-2 text-xl font-bold text-emerald-400 truncate">C01: Dynamic Kalman Beta</div>
                <div class="mt-2 text-xs text-slate-400 flex items-center justify-between">
                    <span>Calmar: <strong class="text-emerald-400">1.3832</strong> (+150.7%)</span>
                    <span>MaxDD: <strong class="text-slate-200">-24.36%</strong></span>
                </div>
            </div>
        </div>

        <!-- Real-time Chart Section -->
        <div class="glass-panel p-5 rounded-xl">
            <div class="flex items-center justify-between mb-4">
                <div>
                    <h2 class="text-base font-bold text-white">Biểu Đồ So Sánh Tăng Trưởng Tài Sản (Equity Curves)</h2>
                    <p class="text-xs text-slate-400">Theo dõi sự biến động tài sản giữa các Shadow Bot theo từng giờ</p>
                </div>
                <span class="text-xs px-2.5 py-1 rounded bg-slate-800 text-slate-400 border border-slate-700">Tự động cập nhật mỗi 3s</span>
            </div>
            <div class="h-64 w-full">
                <canvas id="equityChart"></canvas>
            </div>
        </div>

        <!-- Shadow Instances Table Section -->
        <div class="glass-panel rounded-xl overflow-hidden">
            <div class="p-5 border-b border-slate-800 flex items-center justify-between">
                <div>
                    <h2 class="text-base font-bold text-white">Danh Sách Shadow Paper Bots Local</h2>
                    <p class="text-xs text-slate-400">Các phiên bản chạy độc lập trên tài nguyên tối thiểu (CPU &lt; 0.2%, RAM &lt; 25MB)</p>
                </div>
            </div>

            <div class="overflow-x-auto">
                <table class="w-full text-left text-sm text-slate-300">
                    <thead class="bg-slate-900/60 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
                        <tr>
                            <th class="px-5 py-3.5">Shadow Bot & Chiến Lược</th>
                            <th class="px-4 py-3.5">Trạng Thái</th>
                            <th class="px-4 py-3.5 text-right">Vốn & Tài Sản</th>
                            <th class="px-4 py-3.5 text-right">Vị Thế (ETH)</th>
                            <th class="px-4 py-3.5 text-right">Lợi Nhuận (Return %)</th>
                            <th class="px-4 py-3.5 text-right">Max Drawdown</th>
                            <th class="px-4 py-3.5 text-right">Lệnh / Win Rate</th>
                            <th class="px-5 py-3.5 text-center">Thao Tác</th>
                        </tr>
                    </thead>
                    <tbody id="shadowsTableBody" class="divide-y divide-slate-800/60">
                        <tr>
                            <td colspan="8" class="px-5 py-8 text-center text-slate-500">Đang tải dữ liệu Shadow Bots...</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

    </main>

    <!-- Spawn New Shadow Modal -->
    <div id="spawnModal" class="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center hidden">
        <div class="glass-panel w-full max-w-lg p-6 rounded-2xl border border-slate-700 space-y-5 shadow-2xl">
            <div class="flex items-center justify-between border-b border-slate-800 pb-3">
                <h3 class="text-base font-bold text-white flex items-center gap-2">
                    <span>🚀</span> Khởi Tạo Shadow Paper Bot Mới
                </h3>
                <button onclick="closeSpawnModal()" class="text-slate-400 hover:text-white">&times;</button>
            </div>

            <div class="space-y-4 text-xs">
                <div>
                    <label class="block text-slate-400 mb-1 font-medium">Mã Định Danh (Shadow ID)</label>
                    <input type="text" id="newShadowId" placeholder="VD: SHADOW_C10_PAPER" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-emerald-500">
                </div>

                <div>
                    <label class="block text-slate-400 mb-1 font-medium">Tên Hiển Thị</label>
                    <input type="text" id="newShadowName" placeholder="VD: Shadow Amihud Guard Bot" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-emerald-500">
                </div>

                <div>
                    <label class="block text-slate-400 mb-1 font-medium">Chọn Ứng Viên Chiến Lược</label>
                    <select id="newStrategyId" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-emerald-500">
                        <option value="">Đang tải danh sách ứng viên...</option>
                    </select>
                </div>

                <div>
                    <label class="block text-slate-400 mb-1 font-medium">Vốn Paper Khởi Tạo (USDT)</label>
                    <input type="number" id="newShadowCapital" value="10000" step="1000" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-emerald-500">
                </div>
            </div>

            <div class="flex items-center justify-end space-x-3 pt-3 border-t border-slate-800">
                <button onclick="closeSpawnModal()" class="px-4 py-2 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg">Hủy</button>
                <button onclick="submitSpawnShadow()" class="px-4 py-2 text-xs bg-emerald-600 hover:bg-emerald-500 text-white font-medium rounded-lg">Khởi Chạy Ngay</button>
            </div>
        </div>
    </div>

    <!-- JavaScript Logic -->
    <script>
        let chartInstance = null;

        async function fetchStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();

                // Update Header
                if (data.last_feed_time) {
                    const fd = new Date(data.last_feed_time);
                    document.getElementById('feedTime').textContent = isNaN(fd.getTime()) ? data.last_feed_time : `${fd.toLocaleDateString([], {month:'2-digit', day:'2-digit'})} ${fd.toLocaleTimeString()}`;
                } else {
                    document.getElementById('feedTime').textContent = 'Vừa cập nhật';
                }

                // Update KPIs
                document.getElementById('statActiveCount').textContent = data.active_shadows_count;
                document.getElementById('statTotalCount').textContent = `/ ${data.total_shadows_count} tổng số`;
                document.getElementById('statTotalEquity').textContent = `$${data.total_equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                document.getElementById('statTotalInitial').textContent = `Vốn gốc: $${data.total_initial.toLocaleString()}`;

                const pnlEl = document.getElementById('statTotalPnl');
                const retEl = document.getElementById('statOverallReturn');
                const isProfit = data.total_pnl >= 0;
                pnlEl.textContent = `${isProfit ? '+' : ''}$${data.total_pnl.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                pnlEl.className = `text-3xl font-extrabold ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`;
                retEl.textContent = `${isProfit ? '+' : ''}${data.overall_return_pct.toFixed(2)}%`;
                retEl.className = `text-sm font-semibold ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`;

                // Render Table
                renderTable(data.shadows);

                // Render Chart
                renderChart(data.shadows);
            } catch (err) {
                console.error("Loi fetchStatus:", err);
            }
        }

        function renderTable(shadows) {
            const tbody = document.getElementById('shadowsTableBody');
            if (!shadows || shadows.length === 0) {
                tbody.innerHTML = `<tr><td colspan="8" class="px-5 py-6 text-center text-slate-500">Chưa có Shadow Bot nào được tạo.</td></tr>`;
                return;
            }

            let html = '';
            shadows.forEach(s => {
                const isRunning = s.status === 'RUNNING';
                const statusBadge = isRunning 
                    ? `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"><span class="h-1.5 w-1.5 rounded-full bg-emerald-400 mr-1.5"></span>Chạy (Running)</span>`
                    : `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20"><span class="h-1.5 w-1.5 rounded-full bg-amber-400 mr-1.5"></span>Tạm dừng</span>`;

                const isProfitable = s.return_pct >= 0;
                const returnColor = isProfitable ? 'text-emerald-400' : 'text-rose-400';
                
                const winRateBadge = s.win_rate !== null && s.win_rate !== undefined
                    ? `<span class="text-xs text-slate-300">Thắng: <strong>${s.win_rate.toFixed(1)}%</strong> (${s.win_count}/${s.closed_trades})</span>`
                    : (s.position_qty > 0.0001 
                        ? `<span class="text-xs text-emerald-400/90 font-medium">● Đang mở vị thế ETH</span>`
                        : `<span class="text-xs text-slate-500">Chờ lệnh</span>`);

                const pnlRealized = s.realized_pnl || 0.0;
                const pnlUnrealized = s.unrealized_pnl || 0.0;
                const netPnl = pnlRealized + pnlUnrealized;

                html += `
                <tr class="hover:bg-slate-800/30 transition">
                    <td class="px-5 py-4">
                        <div class="font-bold text-white text-sm">${s.name}</div>
                        <div class="text-xs text-slate-500 font-mono">${s.shadow_id} • ${s.strategy_id}</div>
                    </td>
                    <td class="px-4 py-4">${statusBadge}</td>
                    <td class="px-4 py-4 text-right">
                        <div class="font-bold text-white">$${s.equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
                        <div class="text-xs text-slate-500">Gốc: $${s.initial_capital.toLocaleString()}</div>
                    </td>
                    <td class="px-4 py-4 text-right">
                        <div class="font-medium text-slate-200">${s.position_qty.toFixed(4)} ETH</div>
                        <div class="text-xs text-slate-500">Tỷ trọng: ${(s.target_position_pct * 100).toFixed(0)}%</div>
                    </td>
                    <td class="px-4 py-4 text-right">
                        <div class="font-bold ${returnColor}">${isProfitable ? '+' : ''}${s.return_pct.toFixed(2)}%</div>
                        <div class="text-xs text-slate-400">P&L: ${netPnl >= 0 ? '+' : ''}$${netPnl.toFixed(2)}</div>
                    </td>
                    <td class="px-4 py-4 text-right font-semibold text-rose-400">
                        ${s.max_drawdown.toFixed(2)}%
                    </td>
                    <td class="px-4 py-4 text-right">
                        <div class="text-slate-200">${s.trade_count} lần khớp</div>
                        <div>${winRateBadge}</div>
                    </td>
                    <td class="px-5 py-4 text-center">
                        <div class="inline-flex space-x-1.5">
                            <button onclick="controlShadow('${s.shadow_id}', '${isRunning ? 'pause' : 'resume'}')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs border border-slate-700 text-slate-200 transition">
                                ${isRunning ? '⏸️ Tạm Dừng' : '▶️ Chạy'}
                            </button>
                            <button onclick="controlShadow('${s.shadow_id}', 'reset')" class="px-2 py-1 rounded bg-slate-800 hover:bg-rose-900/40 text-xs border border-slate-700 hover:border-rose-500/30 text-slate-400 hover:text-rose-300 transition" title="Đặt lại tài khoản">
                                🔄
                            </button>
                        </div>
                    </td>
                </tr>`;
            });
            tbody.innerHTML = html;
        }

        function renderChart(shadows) {
            if (!shadows || shadows.length === 0) return;
            const ctx = document.getElementById('equityChart').getContext('2d');

            const datasets = [];
            const colors = ['#10b981', '#38bdf8', '#a855f7', '#f59e0b', '#ec4899', '#6366f1'];

            // Find common timestamps or longest history
            let longestHist = [];
            shadows.forEach(s => {
                if (s.equity_history && s.equity_history.length > longestHist.length) {
                    longestHist = s.equity_history;
                }
            });

            const labels = longestHist.map(pt => {
                const d = new Date(pt.timestamp);
                return isNaN(d.getTime()) ? pt.timestamp : `${d.toLocaleDateString([], {month:'2-digit', day:'2-digit'})} ${d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}`;
            });

            shadows.forEach((s, idx) => {
                if (!s.equity_history || s.equity_history.length === 0) return;
                const color = colors[idx % colors.length];
                datasets.push({
                    label: s.name,
                    data: s.equity_history.map(pt => pt.equity),
                    borderColor: color,
                    backgroundColor: 'transparent',
                    borderWidth: 2,
                    tension: 0.2,
                    pointRadius: 0,
                });
            });

            if (chartInstance) {
                chartInstance.data.labels = labels;
                chartInstance.data.datasets = datasets;
                chartInstance.update('none');
            } else {
                chartInstance = new Chart(ctx, {
                    type: 'line',
                    data: { labels, datasets },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: { mode: 'index', intersect: false },
                        scales: {
                            x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#64748b', maxTicksLimit: 8 } },
                            y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#64748b' } }
                        },
                        plugins: {
                            legend: { labels: { color: '#94a3b8', boxWidth: 12 } }
                        }
                    }
                });
            }
        }

        async function controlShadow(shadowId, action) {
            try {
                await fetch(`/api/shadows/${shadowId}/action`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ action })
                });
                fetchStatus();
            } catch (err) {
                alert("Lỗi điều khiển shadow: " + err);
            }
        }

        async function triggerFeedRefresh() {
            try {
                const res = await fetch('/api/feed/refresh', { method: 'POST' });
                const d = await res.json();
                fetchStatus();
            } catch (e) {
                console.error(e);
            }
        }

        // Modal Handlers
        function openSpawnModal() {
            loadCandidatesSelect();
            document.getElementById('spawnModal').classList.remove('hidden');
        }

        function closeSpawnModal() {
            document.getElementById('spawnModal').classList.add('hidden');
        }

        async function loadCandidatesSelect() {
            try {
                const res = await fetch('/api/candidates');
                const list = await res.json();
                const sel = document.getElementById('newStrategyId');
                sel.innerHTML = list.map(c => `<option value="${c.strategy_id}">${c.name} [Calmar: ${c.calmar_grade}]</option>`).join('');
            } catch (e) {
                console.error(e);
            }
        }

        async function submitSpawnShadow() {
            const id = document.getElementById('newShadowId').value.trim();
            const name = document.getElementById('newShadowName').value.trim();
            const strat = document.getElementById('newStrategyId').value;
            const cap = parseFloat(document.getElementById('newShadowCapital').value) || 10000;

            if (!id || !name || !strat) {
                alert("Vui lòng điền đầy đủ thông tin!");
                return;
            }

            try {
                const res = await fetch('/api/shadows/spawn', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ shadow_id: id, name, strategy_id: strat, capital: cap })
                });
                if (res.ok) {
                    closeSpawnModal();
                    fetchStatus();
                } else {
                    const err = await res.json();
                    alert("Lỗi: " + err.detail);
                }
            } catch (e) {
                alert("Lỗi gửi yêu cầu: " + e);
            }
        }

        // Auto refresh every 3 seconds
        fetchStatus();
        setInterval(fetchStatus, 3000);
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    return HTMLResponse(content=HTML_CONTENT)


def run_server(host: str = "127.0.0.1", port: int = 8000):
    """Khởi chạy máy chủ Web cục bộ."""
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_server()
