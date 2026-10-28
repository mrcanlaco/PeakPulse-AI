import React, { useState, useEffect, useMemo } from 'react';
import {
  X,
  Search,
  BookOpen,
  Lightbulb,
  Target,
  BarChart3,
  Activity,
  Layers,
  FlaskConical,
  ShieldCheck,
  Cpu,
  Clock,
  GitPullRequest,
  Settings,
  Radio,
  ChevronRight,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  Flame,
  Scale,
  Zap,
  Info,
  ShieldAlert,
  Compass,
  Brain
} from 'lucide-react';
import { useTranslation } from '../i18n/LanguageContext';
import type { WorkspaceTab } from './WorkspaceTabBar';

export interface TabHelpModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeTab: WorkspaceTab;
}

type GuideSection = 'OVERVIEW' | 'TABS' | 'PLAYBOOK' | 'MODELS' | 'RISK';

interface TabGuideItem {
  id: WorkspaceTab;
  name: string;
  nameEn: string;
  icon: React.ComponentType<{ className?: string }>;
  category: 'TRADING' | 'LAB' | 'SYSTEM';
  badge?: string;
  purpose: string;
  mechanism: string[];
  metrics: Array<{ label: string; desc: string }>;
  playbook: string[];
}

export const TabHelpModal: React.FC<TabHelpModalProps> = ({
  isOpen,
  onClose,
  activeTab,
}) => {
  const { language } = useTranslation();
  const [activeSection, setActiveSection] = useState<GuideSection>('TABS');
  const [selectedTab, setSelectedTab] = useState<WorkspaceTab>(activeTab);
  const [searchTerm, setSearchTerm] = useState('');

  // Sync selected tab with prop when modal opens
  useEffect(() => {
    if (isOpen) {
      setSelectedTab(activeTab);
      setSearchTerm('');
    }
  }, [isOpen, activeTab]);

  const guides = useMemo<Record<WorkspaceTab, TabGuideItem>>(() => {
    if (language === 'en') {
      return {
        DECISION: {
          id: 'DECISION',
          name: 'Trade Setup',
          nameEn: 'Trade Setup',
          icon: Target,
          category: 'TRADING',
          badge: 'V2 2-Tier Engine',
          purpose: 'Real-time quantitative dashboard showing reference trade setups (Entry, SL, TP1-3, R:R), 15m/5m derivatives charts, and weighted score components.',
          mechanism: [
            'Two-Tier Climax Scoring: Combines macro pump amplitude (Tier 1 HTF) with micro order-flow exhaustion (Tier 2 LTF).',
            'Dynamic Trade Setup: automatically calculates Stop Loss and versioned targets (v2: -8% TP1, -20% core target, -30% runner).',
            'Live Binance Integration: Zero-lag order book ticker, live Funding APR, and Open Interest change rates.',
            'Interactive AI Assistant: Built-in LLM analyst for deep coin breakdown and risk diagnosis.'
          ],
          metrics: [
            { label: 'Distribution Score', desc: 'Quantitative composite score (0-100) indicating top climax exhaustion level.' },
            { label: 'Probability (%)', desc: 'Calibrated empirical probability for the selected model contract; v2 means a 20% drawdown within 24h.' },
            { label: 'Funding APR', desc: 'Annualized funding cost. Highly positive or inverted negative rates highlight liquidation traps.' },
            { label: 'Taker Sell Ratio', desc: 'Percentage of aggressive market sell orders. Values > 55% show institutional dumping.' },
            { label: 'R:R Ratio', desc: 'Reward-to-Risk ratio calculated as (TP1 potential / SL risk).' }
          ],
          playbook: [
            'Check that the signal is in "FIRED" or high-probability "ARMED" state.',
            'Verify that Taker Sell Ratio >= 55% and OI change is stalling or turning negative.',
            'Enter Short within the suggested Entry Zone, set strict Stop Loss as prescribed, and take 50% profit at TP1 (-4%).'
          ]
        },
        RADAR: {
          id: 'RADAR',
          name: 'Signals',
          nameEn: 'Signal Feed',
          icon: Activity,
          category: 'TRADING',
          badge: 'Real-time Feed',
          purpose: '24/7 continuous signal feed detecting distribution tops across all Binance USDT Futures pairs.',
          mechanism: [
            'Continuous Scanner Daemon: Periodically monitors candidate universe and triggers instant climax alerts.',
            '2-Tier State Classification: Labels signals as ARMED (Pre-condition met, waiting for trigger) or FIRED (Active short trigger).',
            'Multi-dimensional Filtering: Filter by Strategic Presets, Sectors (AI, Meme, L1/L2), Market Cap Tiers, and Risk Levels.',
            'Telegram Push Integration: Instant multi-tier push alerts directly to Telegram channels.'
          ],
          metrics: [
            { label: 'FIRED / ARMED State', desc: 'FIRED = Immediate short execution; ARMED = High-alert setup watching for 5m breakdown.' },
            { label: 'Risk Level', desc: 'CRITICAL / HIGH / MEDIUM / SAFE classified by pump amplitude and volatility.' },
            { label: 'Market Cap Tier', desc: 'LARGE (> $1B), MID ($100M - $1B), SMALL (< $100M) sizing.' },
            { label: 'Validity Hours', desc: 'Hours left before signal expiration (default 24h).' }
          ],
          playbook: [
            'Filter by "FIRED" tab to see coins actively breaking down right now.',
            'Use Strategic Presets like "Climax Dump" or "OI Squeeze" for specific trade setups.',
            'Click on any signal card to instantly load its full chart and analytics in the Trade Setup view.'
          ]
        },
        RANKING: {
          id: 'RANKING',
          name: 'Top Dump',
          nameEn: 'Candidate Filter',
          icon: BarChart3,
          category: 'TRADING',
          badge: 'Official V1 Tier-1 Filter',
          purpose: 'Tier 1 uses the single official V1 filter to select and rank potential dump candidates across Binance Futures.',
          mechanism: [
            'Official V1 screening removes coins that fail liquidity, pump-amplitude, and data-quality requirements before scoring.',
            'Risk ranking combines price momentum, OI, funding, taker sell, and volume to surface the strongest candidates first.',
            'Two-step safety gate only enables trade entry when the candidate is fresh and has a valid Radar signal; otherwise analysis remains available.'
          ],
          metrics: [
            { label: 'Rank Score', desc: 'Multi-factor quantitative score ranking highest probability dump candidates.' },
            { label: 'Stage', desc: 'PUMP_ACTIVE, EXHAUSTION, DISTRIBUTION, or DUMPED.' },
            { label: 'P@10 (Precision at 10)', desc: 'Empirical precision among Top 10 ranked candidates.' },
            { label: 'Event Recall', desc: 'Percentage of total market dump events successfully captured.' }
          ],
          playbook: [
            'Focus on candidates in "EXHAUSTION" or "DISTRIBUTION" stage for imminent short setups.',
            'Check probability, data quality, and the live Radar signal before choosing "Enter trade".'
          ]
        },
        WATCHLIST: {
          id: 'WATCHLIST',
          name: 'Positions',
          nameEn: 'Watchlist & PnL',
          icon: Layers,
          category: 'TRADING',
          badge: 'Position Tracker',
          purpose: 'Manage personal coin watchlists, preset scan modes, and track open short positions with live PnL & ROI.',
          mechanism: [
            '5 Scan Presets: Top Volatile, Top Volume, Top Gainers, Top Losers, and Manual Custom Watchlist.',
            'Live Position Tracking: Record Entry Price, Leverage, SL, TP, and monitor real-time unrealized PnL & ROI%.',
            'Local & Server Sync: Watchlist persists across browser sessions and syncs with scanner daemon.'
          ],
          metrics: [
            { label: 'Position PnL ($)', desc: 'Real-time dollar profit/loss based on live Binance market price.' },
            { label: 'Position ROI (%)', desc: 'Percentage return on margin considering leverage.' },
            { label: 'Signal Progress (%)', desc: 'Progress from Entry to the target stored on the selected model signal.' }
          ],
          playbook: [
            'Add coins from Radar or Ranking directly to Tracking Watchlist with one click.',
            'Log your executed trade details to monitor live SL/TP trailing without switching to exchange.'
          ]
        },
        MULTISCAN: {
          id: 'MULTISCAN',
          name: 'Multi-Scan',
          nameEn: 'Multi-Timeframe',
          icon: Radio,
          category: 'LAB',
          badge: 'Multi-TF',
          purpose: 'Multi-timeframe correlation scanner analyzing market-wide volatility across 5m, 15m, 1h, 4h, and 1D.',
          mechanism: [
            'Cross-Timeframe Volatility Matrix: Evaluates synchronized climax patterns across all standard trading frames.',
            'Historical Run Registry: Archives multi-coin scan runs and volatility breakdown artifacts.'
          ],
          metrics: [
            { label: 'Timeframe Alignment', desc: 'Synchronization index across 5m, 15m, 1h, 4h trends.' },
            { label: 'Artifact Runs', desc: 'Total historical scan batches archived for quant verification.' }
          ],
          playbook: [
            'Use Multi-Scan to identify broader sector pumps when multiple related tokens hit climax simultaneously.'
          ]
        },
        BACKTEST: {
          id: 'BACKTEST',
          name: 'Backtest',
          nameEn: 'Validation Lab',
          icon: FlaskConical,
          category: 'LAB',
          badge: 'Saved Runs',
          purpose: 'Empirical validation lab for evaluating strategy performance on stored historical periods.',
          mechanism: [
            'Purged & Embargoed Walk-Forward Cross Validation: Trains on earlier periods and evaluates on later periods with point-in-time safeguards.',
            'Leakage Audit Suite: Automated checks designed to detect future-data contamination; passing them reduces risk but is not absolute proof.',
            'Metric Distributions: Precision mean, baseline comparisons, Brier calibration, and drawdown distributions.'
          ],
          metrics: [
            { label: 'Precision Mean', desc: 'Average precision across all validation folds.' },
            { label: 'Baseline Precision', desc: 'Precision of random / heuristic benchmark for edge verification.' },
            { label: 'Brier Calibration', desc: 'Calibration error score (lower = better probability fidelity).' }
          ],
          playbook: [
            'Inspect backtest artifacts to verify mathematical edge before deploying modified trading rules.'
          ]
        },
        FORWARD: {
          id: 'FORWARD',
          name: 'Forward Test',
          nameEn: 'Out-of-Sample',
          icon: Sparkles,
          category: 'LAB',
          badge: 'Frozen ML',
          purpose: 'Out-of-sample live simulation evaluating frozen Machine Learning models on unseen market periods.',
          mechanism: [
            'Frozen Model Artifacts: Bundled LightGBM models + Isotonic Calibrators stored with immutable hashes.',
            'Out-of-Sample Evaluation: Evaluates performance against live collected market outcomes.'
          ],
          metrics: [
            { label: 'Frozen Model ID', desc: 'Immutable identifier of the production ML model checkpoint.' },
            { label: 'OOS Precision', desc: 'Live out-of-sample precision on newly recorded market cycles.' }
          ],
          playbook: [
            'Compare performance across different frozen models to select the champion checkpoint.'
          ]
        },
        AUDIT: {
          id: 'AUDIT',
          name: 'Audit',
          nameEn: 'Audit Matrix',
          icon: ShieldCheck,
          category: 'LAB',
          badge: 'Diagnostics',
          purpose: 'Deep machine learning diagnostics, confusion matrices, probability calibration curves, and feature importance.',
          mechanism: [
            'Confusion Matrix: True Positives (TP), False Positives (FP), True Negatives (TN), False Negatives (FN).',
            'Reliability Curve: Brier score calibration mapping forecasted probability vs actual empirical frequency.'
          ],
          metrics: [
            { label: 'ROC-AUC', desc: 'Area Under the ROC Curve measuring model discriminative power.' },
            { label: 'F1 Score', desc: 'Harmonic mean of Precision and Recall.' },
            { label: 'Target Drawdown Benchmark', desc: 'Standard target: >= 8% drawdown with <= 4% MAE.' }
          ],
          playbook: [
            'Use reliability curves and uncertainty bands to check whether forecast bins align with observed outcomes; never assume exact calibration.'
          ]
        },
        MARKET: {
          id: 'MARKET',
          name: 'Market',
          nameEn: 'Market & Alpha',
          icon: Activity,
          category: 'SYSTEM',
          badge: 'Alpha Lab',
          purpose: 'Comprehensive Binance listing intelligence, market regime diagnostics (ADX/BB), Meta-labeling filter, and Drift Guardian.',
          mechanism: [
            'Binance Listing Breakdown: Uses the latest API payload to summarize Spot and Futures coverage.',
            'Market Regime Classifier: Identifies Trending Bear / Bull / Choppy regimes to adjust risk multipliers.',
            'Meta-Labeling Engine: When configured, a secondary model can veto weak signals; effectiveness must come from a versioned evaluation report.',
            'Drift Guardian: Continuous Population Stability Index (PSI) monitoring to detect alpha decay.'
          ],
          metrics: [
            { label: 'Market Regime', desc: 'Current macro market state (e.g. TRENDING_BEAR, CHOPPY, RANGE).' },
            { label: 'ADX Trend Strength', desc: 'Average Directional Index (> 25 indicates strong directional trend).' },
            { label: 'Drift Status', desc: 'HEALTHY / WARNING / CRITICAL based on feature distribution drift.' }
          ],
          playbook: [
            'Use Market Regime as risk context, not as a guarantee that a Short setup will succeed.'
          ]
        },
        TELEMETRY: {
          id: 'TELEMETRY',
          name: 'Telemetry',
          nameEn: 'System Health',
          icon: Cpu,
          category: 'SYSTEM',
          badge: '24/7 Monitor',
          purpose: 'Real-time scanner daemon health monitor, memory/CPU usage, cycle duration, and Telegram bot status.',
          mechanism: [
            'Scanner Heartbeat: Monitors live daemon polling cycles every 5 minutes.',
            'Resource Telemetry: CPU %, Memory RSS (MB), DuckDB locks, and queue lengths.'
          ],
          metrics: [
            { label: 'Daemon Status', desc: 'RUNNING / IDLE / OFFLINE state of the background scanner.' },
            { label: 'Cycle Duration', desc: 'Time taken in seconds to scan and score all coins in universe.' },
            { label: 'Scanned Coins Count', desc: 'Number of active coins processed in latest cycle.' }
          ],
          playbook: [
            'Verify daemon is RUNNING with recent heartbeat timestamp to ensure continuous market protection.'
          ]
        },
        HISTORY: {
          id: 'HISTORY',
          name: 'History',
          nameEn: 'Archive & DB',
          icon: Clock,
          category: 'SYSTEM',
          badge: 'DuckDB',
          purpose: 'Historical signal archives, daily alert counts, DuckDB storage inspection, and long-term performance logs.',
          mechanism: [
            'DuckDB Aggregation: Daily timeline of signals issued, hit rates, and scan frequencies.',
            'Historical Data Stats: Min/Max timestamps of collected derivatives tables.'
          ],
          metrics: [
            { label: 'Signals per Day', desc: 'Historical daily count of fired alerts and successful target hits.' },
            { label: 'Scan Cycles per Day', desc: 'Daily execution volume of 24/7 scanning daemon.' }
          ],
          playbook: [
            'Review multi-day performance trends to track signal frequency across different market weeks.'
          ]
        },
        MODELS: {
          id: 'MODELS',
          name: 'Models & Architecture',
          nameEn: 'Models & Architecture',
          icon: Brain,
          category: 'SYSTEM',
          badge: 'ML & Regimes',
          purpose: 'Detailed documentation of machine learning models, 2-tier heuristics, market regime gating, and historical validation milestones.',
          mechanism: [
            '3-Engine Architecture: V1 Heuristic (9-component distribution score), V2 Two-Tier Climax (HTF Armed / LTF Fired), and Frozen ML Pipeline (LightGBM/LogReg).',
            'Regime Gate: ADX/BB/EMA filter that allows signals in SIDEWAY_DISTRIBUTION and TRENDING_BEAR while suppressing TRENDING_BULL & HIGH_VOLATILITY noise.',
            'Calibration: Isotonic Regression maps raw scores to probabilities; quality is reported for each frozen Model ID.'
          ],
          metrics: [
            { label: 'Production Model ID', desc: 'Immutable identifier loaded by the current live configuration.' },
            { label: 'Release Evidence', desc: 'Checksums, cutoff, threshold, and metrics recorded for that exact model bundle.' },
            { label: 'Forward Evidence', desc: 'Post-cutoff outcomes reported only after enough matching samples are available.' }
          ],
          playbook: [
            'Consult the feature importance rankings and regime matrix before trading new signal setups.'
          ]
        },
        UPDATES: {
          id: 'UPDATES',
          name: 'Updates',
          nameEn: 'Git & Releases',
          icon: GitPullRequest,
          category: 'SYSTEM',
          badge: 'v2.0 Pro',
          purpose: 'Git commit history, architectural milestones, development metrics, and deployed release identity.',
          mechanism: [
            'Release Pipeline: Production deploys an exact commit only after CI succeeds; direct server auto-update is disabled.',
            'Git Analytics: Commit classification (feat, fix, perf, docs) and active development days.'
          ],
          metrics: [
            { label: 'Current Commit', desc: 'Active Git commit hash deployed on server.' },
            { label: 'Update Status', desc: 'Displays whether newer commits exist on GitHub origin/main.' }
          ],
          playbook: [
            'Use this page to inspect version status; production changes are applied through the release pipeline.'
          ]
        },
        SETTINGS: {
          id: 'SETTINGS',
          name: 'Settings',
          nameEn: 'Settings & AI',
          icon: Settings,
          category: 'SYSTEM',
          badge: 'Config',
          purpose: 'AI Assistant LLM configuration (OpenAI/DeepSeek/Gemini), scanner parameters, alert thresholds, and language preferences.',
          mechanism: [
            'AI Provider Key Management: Secure API key configuration for interactive LLM market analysis.',
            'UI Customization: GUI version selection (V1 / V2), alert sound toggles, and language switching.'
          ],
          metrics: [
            { label: 'AI Provider', desc: 'Selected LLM provider for AI Executive Briefings.' },
            { label: 'Alert Score Threshold', desc: 'Minimum distribution score required to trigger alert.' }
          ],
          playbook: [
            'Configure your Gemini / DeepSeek API key to unlock the Interactive AI Assistant in the Decision Center.'
          ]
        },
        FIBO_SHORT: {
          id: 'FIBO_SHORT',
          name: 'Fibo Short (H4/D1)',
          nameEn: 'Confirmed Reversal & Fibo Short',
          icon: GitPullRequest,
          category: 'TRADING',
          badge: 'H4/D1 → H1 Trigger',
          purpose: 'Wait for a confirmed bearish reversal wave on H4 or D1, measure Fibonacci retracement into the Golden Pocket (0.500–0.618), and enter Short on a closed H1 confirmation candle.',
          mechanism: [
            'HTF Reversal Wave (H4/D1): Identifies a valid Swing High (1.0) followed by a bearish reversal candle and downward impulse wave to Impulse Low (0.0).',
            'Fibonacci Price Grid: Draws Golden Pocket (0.500–0.618), SL above Swing High (1.0 + 0.2 ATR), and TP1 (0.0), TP2 (Ext 1.272), TP3 (Ext 1.618).',
            'H1 Confirmation Trigger (1+2): Closed H1 red candle (close < open, price_ret_1h <= 0) + Bearish Candle Pattern (Cond 1) + Break of Previous H1 Low / Fibo 0.5 (Cond 2).'
          ],
          metrics: [
            { label: 'Swing High (1.0) → Impulse Low (0.0)', desc: 'Defines the structural bearish wave on H4 or D1.' },
            { label: 'Golden Pocket (0.500–0.618)', desc: 'Optimal Fibonacci retracement entry zone for trend-following Short.' },
            { label: 'In-Sample Backtest (≤ 2025)', desc: 'Historical verification strictly locked at <= 2025-12-31 so 2026+ remains untouched for Out-of-Sample (OOS).' }
          ],
          playbook: [
            'Wait for stage "FIRED_CONFIRMED_SHORT" when both H4/D1 Fibo pullback and H1 confirmation rules are satisfied.',
            'Place Stop Loss above Swing High (Fibo 1.0 + ATR buffer) and scale out at TP1 (Fibo 0.0), TP2 (Ext 1.272), and TP3 (Ext 1.618).'
          ]
        }
      };
    }

    // Default: Tiếng Việt (Vietnamese)
    return {
      DECISION: {
        id: 'DECISION',
        name: 'Vào lệnh',
        nameEn: 'Trade Setup',
        icon: Target,
        category: 'TRADING',
        badge: 'V2 2-Tier Climax Engine',
        purpose: 'Buồng lái ra quyết định giao dịch theo thời gian thực — cung cấp kế hoạch vào lệnh chuẩn xác (Entry, Stop Loss, TP1-3, R:R), biểu đồ nến 15m/5m live phái sinh và trợ lý AI phân tích chuyên sâu.',
        mechanism: [
          'Chấm điểm Phân phối 2 Tầng (2-Tier Climax Scoring): Kết hợp biên độ bơm vĩ mô khung 1h/4h/24h (Tầng 1) với dấu hiệu xả vi mô dòng lệnh 5m/15m (Tầng 2).',
          'Kế hoạch Trade Setup Động: tự tính Stop Loss và các nấc mục tiêu theo contract (v2: -8% TP1, -20% mục tiêu chính, -30% runner).',
          'Tích hợp Trực tiếp Binance Live: Cập nhật giá, funding rate APR, biến động OI và tỷ lệ Taker Sell theo từng giây.',
          'Trợ lý AI Đàm Thoại: Chat với AI để tóm tắt bằng chứng rủi ro, thành phần điểm có trọng số và dữ liệu cần cho quản trị vốn.'
        ],
        metrics: [
          { label: 'Điểm Phân Phối (Distribution Score)', desc: 'Điểm số định lượng (0-100) đánh giá mức độ kiệt sức và tạo đỉnh phân phối.' },
          { label: 'Xác Suất Xả (AI) (%)', desc: 'Xác suất thực nghiệm theo contract của model; với v2 là khả năng giá giảm ít nhất 20% trong 24h.' },
          { label: 'Funding Rate & APR', desc: 'Tỷ lệ phí funding quy đổi ra %/năm. Giúp nhận diện bẫy ép lệnh Long/Short.' },
          { label: 'Taker Sell Ratio', desc: 'Tỷ lệ lệnh bán chủ động cắn qua giá bid. Vượt > 55% cho thấy phe bán tổ chức đang xả mạnh.' },
          { label: 'Tỷ Lệ R:R (Risk/Reward)', desc: 'Tỷ lệ lợi nhuận / rủi ro tính theo (Biên độ TP1 / Biên độ SL).' }
        ],
        playbook: [
          'Kiểm tra tín hiệu xem đang ở trạng thái "Đã kích hoạt" (đang xả) hay "Đang sẵn sàng".',
          'Đối chiếu Taker Sell Ratio >= 55% và Open Interest bắt đầu giảm hoặc đi ngang.',
          'Vào lệnh Short trong Vùng Entry gợi ý, cài SL nghiêm ngặt và chốt lời 50% vị thế tại TP1 (-4%).'
        ]
      },
      RADAR: {
        id: 'RADAR',
        name: 'Tín hiệu',
        nameEn: 'Signal Feed',
        icon: Activity,
        category: 'TRADING',
        badge: 'Feed Trực Tiếp 24/7',
        purpose: 'Bảng theo dõi dòng tín hiệu phân phối đỉnh hoạt động liên tục 24/7 trên toàn bộ các cặp coin USDT Futures sàn Binance.',
        mechanism: [
          'Tiến trình Quét Tự động: Quét toàn thị trường định kỳ 5 phút/lần và phát hiện ngay lập tức các coin đạt điểm phân phối.',
          'Phân loại trạng thái hai tầng: "Đang sẵn sàng" khi tiền điều kiện đã đạt và đang canh nến đảo chiều; "Đã kích hoạt" khi tín hiệu xả xuất hiện.',
          'Bộ lọc Chiến lược Đa chiều: Lọc theo Preset (Climax Dump, Bẫy Funding, OI Squeeze), Sector (AI, Meme, L1/L2), Vốn hóa và Mức độ rủi ro.',
          'Đẩy Cảnh báo Telegram: Tự động gửi cảnh báo phân tích chất lượng cao về nhóm Telegram.'
        ],
        metrics: [
          { label: 'Trạng thái kích hoạt / sẵn sàng', desc: 'Đã kích hoạt = Có điểm vào lệnh Short; Đang sẵn sàng = Đang tạo đỉnh, chờ nến 5m xác nhận.' },
          { label: 'Mức Độ Rủi Ro (Risk Level)', desc: 'Phân cấp CRITICAL / HIGH / MEDIUM / SAFE dựa trên biến động và biên độ bơm.' },
          { label: 'Phân Hạng Vốn Hóa', desc: 'LARGE (> $1B), MID ($100M - $1B), SMALL (< $100M).' },
          { label: 'Thời Gian Hiệu Lực', desc: 'Số giờ còn lại trước khi tín hiệu hết hạn (mặc định 24h).' }
        ],
        playbook: [
          'Chọn tab "Đã kích hoạt" để xem các coin đang trong nhịp xả rõ nhất ở hiện tại.',
          'Sử dụng các Preset chiến lược như "Climax Dump" hoặc "Bẫy Funding" để tìm setup theo sở trường.',
          'Bấm vào bất kỳ thẻ tín hiệu nào để mở ngay biểu đồ chi tiết bên màn hình Vào Lệnh.'
        ]
      },
      RANKING: {
        id: 'RANKING',
        name: 'Top coin xả',
        nameEn: 'Candidate Filter',
        icon: BarChart3,
        category: 'TRADING',
        badge: 'Bộ Lọc V1 Chính Thức',
        purpose: 'Tầng 1 dùng duy nhất bộ lọc V1 để chọn và xếp hạng các ứng viên xả tiềm năng từ Binance Futures.',
        mechanism: [
          'Bộ lọc V1 chính thức: loại coin không đạt thanh khoản, biên độ bơm và điều kiện chất lượng dữ liệu trước khi chấm điểm.',
          'Xếp hạng rủi ro: tổng hợp động lượng giá, OI, funding, taker sell và volume để đưa các ứng viên đáng chú ý nhất lên đầu.',
          'Chốt an toàn hai tầng: ứng viên chỉ được phép vào lệnh khi còn mới và có tín hiệu Radar hợp lệ; nếu chưa đủ điều kiện thì chỉ cho phép phân tích.'
        ],
        metrics: [
          { label: 'Điểm Rank Score', desc: 'Điểm tổng hợp định lượng xếp hạng các ứng viên có xác suất sập cao nhất.' },
          { label: 'Giai Đoạn (Stage)', desc: 'PUMP_ACTIVE (Đang bơm), EXHAUSTION (Kiệt sức), DISTRIBUTION (Phân phối), DUMPED (Đã xả).' },
          { label: 'P@10 (Độ chính xác Top 10)', desc: 'Tỷ lệ chính xác thực nghiệm trong Top 10 ứng viên đứng đầu.' },
          { label: 'Event Recall', desc: 'Tỷ lệ bắt trọn các đợt sập đỉnh lớn của thị trường.' }
        ],
        playbook: [
          'Ưu tiên chọn các coin ở giai đoạn "EXHAUSTION" hoặc "DISTRIBUTION" để chuẩn bị lệnh Short đón đầu.',
          'Kiểm tra xác suất, chất lượng dữ liệu và tín hiệu Radar trước khi bấm "Vào lệnh".'
        ]
      },
      WATCHLIST: {
        id: 'WATCHLIST',
        name: 'Vị thế',
        nameEn: 'Tracking Watchlist',
        icon: Layers,
        category: 'TRADING',
        badge: 'Quản Lý PnL',
        purpose: 'Quản lý danh mục coin theo dõi cá nhân, các chế độ quét tự động và ghi nhận quản trị vị thế Short thực tế với PnL & ROI live.',
        mechanism: [
          '5 Chế độ Preset: Top Biến động, Top Volume, Top Tăng giá, Top Giảm giá và Watchlist tùy chọn.',
          'Theo Dõi Vị Thế Trực Tiếp: Lưu giá Entry, Đòn bẩy, SL, TP và tự động tính toán PnL, ROI% theo thời gian thực.',
          'Đồng Bộ Dữ Liệu: Lưu trữ trên trình duyệt và tự động đồng bộ với Daemon quét thị trường.'
        ],
        metrics: [
          { label: 'PnL Vị Thế ($)', desc: 'Lợi nhuận/thua lỗ danh nghĩa dựa theo giá thị trường Binance hiện tại.' },
          { label: 'ROI Vị Thế (%)', desc: 'Tỷ suất sinh lời trên vốn ký quỹ có tính đòn bẩy.' },
          { label: 'Tiến Độ Tín Hiệu (%)', desc: 'Thanh tiến trình từ Entry đến mục tiêu được lưu trên tín hiệu của model.' }
        ],
        playbook: [
          'Thêm coin trực tiếp từ Radar hoặc Top coin xả vào Vị thế chỉ với 1 click.',
          'Ghi nhận thông số vào lệnh thực tế để theo dõi lãi/lỗ mà không cần mở sàn giao dịch.'
        ]
      },
      MULTISCAN: {
        id: 'MULTISCAN',
        name: 'Quét đa khung',
        nameEn: 'Multi-Coin Scan',
        icon: Radio,
        category: 'LAB',
        badge: 'Đa Khung 5m-1D',
        purpose: 'Bộ quét phân tích tương quan đa khung thời gian (5m, 15m, 1h, 4h, 1D) nhằm phát hiện sóng bơm xả đồng pha trên toàn thị trường.',
        mechanism: [
          'Ma Trận Biến Động Đa Khung: Đánh giá sự đồng thuận xu hướng tạo đỉnh giữa khung nến siêu ngắn và khung nến lớn.',
          'Lịch Sử Quét Đa Coin: Lưu trữ các đợt quét toàn thị trường để đối soát và nghiên cứu định lượng.'
        ],
        metrics: [
          { label: 'Độ Đồng Thuận Đa Khung', desc: 'Chỉ số đo lường sự trùng khớp tín hiệu giữa các khung 5m, 15m, 1h, 4h.' },
          { label: 'Lượt Chạy Quét (Runs)', desc: 'Tổng số lượt quét đa coin đã được lưu trữ trong kho lưu trữ.' }
        ],
        playbook: [
          'Dùng Quét đa khung để nhận diện khi cả một nhóm coin cùng hệ (Meme, AI) đồng loạt tạo đỉnh phân phối.'
        ]
      },
      BACKTEST: {
        id: 'BACKTEST',
        name: 'Backtest',
        nameEn: 'Backtest Lab',
        icon: FlaskConical,
        category: 'LAB',
        badge: 'Các Lần Chạy Đã Lưu',
        purpose: 'Phòng thí nghiệm kiểm định hiệu quả thuật toán trên các giai đoạn dữ liệu lịch sử đã lưu.',
        mechanism: [
          'Kiểm Định Cuốn Chiếu (Walk-Forward Validation + Embargo): Huấn luyện trên giai đoạn trước, đánh giá trên giai đoạn sau và áp dụng bảo vệ point-in-time.',
          'Kiểm Toán Rò Rỉ Dữ Liệu: Bộ test tự động được thiết kế để phát hiện việc dùng dữ liệu tương lai; kết quả đạt giúp giảm rủi ro chứ không phải bằng chứng tuyệt đối.',
          'Phân Phối Kết Quả: Thống kê Precision trung bình, Baseline đối chứng, Brier calibration và phân bố qua các fold.'
        ],
        metrics: [
          { label: 'Precision Mean', desc: 'Độ chính xác trung bình qua tất cả các đợt kiểm định cuốn chiếu.' },
          { label: 'Baseline Precision', desc: 'Độ chính xác của phương pháp ngẫu nhiên / quy tắc đơn giản dùng để chứng minh lợi thế (Alpha).' },
          { label: 'Brier Score', desc: 'Độ chuẩn xác của xác suất (càng thấp càng tốt, lý tưởng < 0.15).' }
        ],
        playbook: [
          'Kiểm tra kết quả backtest của từng giả thuyết trước khi áp dụng tham số mới vào hệ thống chạy thực.'
        ]
      },
      FORWARD: {
        id: 'FORWARD',
        name: 'Forward Test',
        nameEn: 'Mô Hình Đóng Băng',
        icon: Sparkles,
        category: 'LAB',
        badge: 'Frozen ML',
        purpose: 'Đánh giá các mô hình Machine Learning đóng băng (Frozen LightGBM) trên tập dữ liệu ngoài mẫu (Out-of-Sample) để chống Overfitting.',
        mechanism: [
          'Mô Hình Đóng Băng (Frozen Model): Đóng gói trọng số mô hình LightGBM + Isotonic Calibrator kèm mã băm Checksum bất biến.',
          'Đánh Giá Ngoài Mẫu: So sánh xác suất dự báo với kết quả thực tế phát sinh sau thời điểm đóng băng.'
        ],
        metrics: [
          { label: 'Mã Mô Hình (Model ID)', desc: 'Định danh duy nhất của phiên bản mô hình ML được đóng băng.' },
          { label: 'OOS Precision', desc: 'Độ chính xác thực tế trên các chu kỳ thị trường mới chưa từng xuất hiện trong tập huấn luyện.' }
        ],
        playbook: [
          'So sánh hiệu năng giữa các phiên bản mô hình đóng băng để chọn ra bản Champion tối ưu nhất.'
        ]
      },
      AUDIT: {
        id: 'AUDIT',
        name: 'Kiểm định',
        nameEn: 'Model Audit',
        icon: ShieldCheck,
        category: 'LAB',
        badge: 'Chẩn Đoán ML',
        purpose: 'Chẩn đoán chi tiết chất lượng mô hình Machine Learning: Ma trận nhầm lẫn (Confusion Matrix), đường cong hiệu chuẩn Brier và độ quan trọng của đặc trưng.',
        mechanism: [
          'Ma Trận Nhầm Lẫn (Confusion Matrix): Phân tích chi tiết số ca Đúng Dương tính (TP), Sai Dương tính (FP), Đúng Âm tính (TN), Sai Âm tính (FN).',
          'Đường Cong Hiệu Chuẩn (Calibration Curve): Đối chiếu xác suất AI dự báo so với tần suất sụt giảm thực tế.'
        ],
        metrics: [
          { label: 'ROC-AUC', desc: 'Diện tích dưới đường cong ROC đo lường khả năng phân biệt đỉnh của mô hình.' },
          { label: 'F1-Score', desc: 'Trung bình điều hòa giữa Precision (Độ chính xác) và Recall (Độ bao quát).' },
          { label: 'Tiêu Chuẩn Target', desc: 'Quy chuẩn: Giá giảm >= 8% trong 24h và độ giật ngược MAE <= 4%.' }
        ],
        playbook: [
          'Dùng đường cong hiệu chuẩn và khoảng bất định để kiểm tra các nhóm xác suất; không giả định xác suất dự báo khớp tuyệt đối với thực tế.'
        ]
      },
      MARKET: {
        id: 'MARKET',
        name: 'Thị trường',
        nameEn: 'Market & Alpha',
        icon: Activity,
        category: 'SYSTEM',
        badge: 'Alpha Lab Guardian',
        purpose: 'Báo cáo phạm vi Binance từ payload mới nhất, trạng thái thị trường (Market Regime), cấu hình Meta-labeling và kết quả Drift Guardian khi có dữ liệu.',
        mechanism: [
          'Thống Kê Niêm Yết Binance: Dùng payload API mới nhất để phân loại Spot và Futures.',
          'Bộ Phân Loại Trạng Thái Thị Trường (Market Regime): Dùng ADX và Bollinger Width để xác định thị trường Xu hướng Giảm (Trending Bear) hay Đi ngang (Choppy).',
          'Mô Hình Meta-Labeling (Lớp 2): Khi được cấu hình, mô hình phụ có thể veto tín hiệu yếu; hiệu quả phải đọc từ báo cáo đánh giá có phiên bản.',
          'Drift Guardian: Giám sát chỉ số ổn định dữ liệu (PSI) để phát hiện sớm hiện tượng suy giảm hiệu quả mô hình.'
        ],
        metrics: [
          { label: 'Market Regime', desc: 'Trạng thái vĩ mô hiện tại (ví dụ: TRENDING_BEAR, CHOPPY, RANGE).' },
          { label: 'Độ Mạnh Xu Hướng (ADX)', desc: 'Chỉ số ADX (> 25 biểu thị xu hướng mạnh, thuận lợi cho giao dịch).' },
          { label: 'Trạng Thái Drift Guardian', desc: 'HEALTHY / WARNING / CRITICAL thể hiện mức độ ổn định của các đặc trưng dữ liệu.' }
        ],
        playbook: [
          'Dùng Market Regime làm bối cảnh quản trị rủi ro, không xem đó là bảo đảm một lệnh Short sẽ thành công.'
        ]
      },
      TELEMETRY: {
        id: 'TELEMETRY',
        name: 'Hạ tầng & Log',
        nameEn: 'Scanner Telemetry',
        icon: Cpu,
        category: 'SYSTEM',
        badge: 'Giám Sát 24/7',
        purpose: 'Bảng giám sát sức khỏe của Daemon quét thị trường 24/7, mức tiêu hao RAM/CPU, thời lượng chu kỳ quét và trạng thái bot Telegram.',
        mechanism: [
          'Nhịp Tim Scanner (Heartbeat): Giám sát chu kỳ quét 5 phút/lần của tiến trình ngầm.',
          'Đo Lường Tài Nguyên: Theo dõi CPU %, Memory RSS (MB), khóa cơ sở dữ liệu DuckDB và độ dài hàng đợi.'
        ],
        metrics: [
          { label: 'Trạng Thái Daemon', desc: 'RUNNING / IDLE / OFFLINE thể hiện bộ quét có đang chạy hay không.' },
          { label: 'Thời Lượng Chu Kỳ (Cycle Duration)', desc: 'Số giây cần thiết để quét và chấm điểm toàn bộ coin trong danh sách.' },
          { label: 'Số Coin Quét Trong Chu Kỳ', desc: 'Số lượng coin thực tế được xử lý trong đợt quét gần nhất.' }
        ],
        playbook: [
          'Kiểm tra định kỳ để đảm bảo Daemon luôn ở trạng thái RUNNING với nhịp tim cập nhật liên tục.'
        ]
      },
      HISTORY: {
        id: 'HISTORY',
        name: 'Lịch sử',
        nameEn: 'System History',
        icon: Clock,
        category: 'SYSTEM',
        badge: 'Lưu Trữ DuckDB',
        purpose: 'Lưu trữ toàn bộ nhật ký tín hiệu cảnh báo lịch sử, thống kê tần suất phát tín hiệu theo ngày và cấu trúc cơ sở dữ liệu DuckDB.',
        mechanism: [
          'Tổng Hợp Dữ Liệu DuckDB: Lưu trữ chuỗi thời gian của các tín hiệu phát ra, số ca thành công và số chu kỳ quét mỗi ngày.',
          'Thống Kê Kho Dữ Liệu: Đo lường mốc thời gian Min/Max của các bảng phái sinh thu thập.'
        ],
        metrics: [
          { label: 'Tín Hiệu Theo Ngày', desc: 'Biểu đồ số lượng tín hiệu cảnh báo phát ra và số lần giá sụt giảm thành công.' },
          { label: 'Chu Kỳ Quét Mỗi Ngày', desc: 'Tổng số lượt quét thị trường mà Daemon đã hoàn tất trong ngày.' }
        ],
        playbook: [
          'Xem lại lịch sử nhiều ngày để đánh giá tần suất cơ hội của thị trường trong các giai đoạn biến động khác nhau.'
        ]
      },
      MODELS: {
        id: 'MODELS',
        name: 'Mô hình & Kiến trúc',
        nameEn: 'Models & Architecture',
        icon: Brain,
        category: 'SYSTEM',
        badge: 'ML & Regimes',
        purpose: 'Tài liệu chi tiết về các mô hình Machine Learning, bộ quy tắc 2 tầng, bộ lọc chế độ thị trường (Regime Gate) và lịch sử đánh giá chất lượng qua các mốc kiểm định.',
        mechanism: [
          'Kiến Trúc 3 Động Cơ: V1 Heuristic (9 thành phần phân phối đỉnh), V2 Two-Tier Climax (HTF Armed / LTF Fired), và Frozen ML Pipeline (LightGBM/LogReg).',
          'Bộ Lọc Regime Gate: Dựa trên ADX/BB/EMA chỉ cho phép tín hiệu trong SIDEWAY_DISTRIBUTION và TRENDING_BEAR, chặn nhiễu trong TRENDING_BULL & HIGH_VOLATILITY.',
          'Hiệu Chuẩn Xác Suất: Isotonic Regression ánh xạ điểm thô sang xác suất; chất lượng được báo cáo riêng cho từng Model ID đóng băng.'
        ],
        metrics: [
          { label: 'Model ID Production', desc: 'Định danh bất biến được cấu hình live nạp ở phiên bản đang chạy.' },
          { label: 'Bằng Chứng Phát Hành', desc: 'Checksum, cutoff, threshold và chỉ số gắn với đúng gói mô hình đó.' },
          { label: 'Bằng Chứng Forward', desc: 'Kết quả sau cutoff chỉ được báo cáo khi có đủ mẫu phù hợp.' }
        ],
        playbook: [
          'Tham khảo bảng xếp hạng độ quan trọng đặc trưng (Feature Importance) và ma trận Regime trước khi giao dịch theo tín hiệu.'
        ]
      },
      UPDATES: {
        id: 'UPDATES',
        name: 'Cập nhật',
        nameEn: 'Version & Releases',
        icon: GitPullRequest,
        category: 'SYSTEM',
        badge: 'v2.0 Pro',
        purpose: 'Theo dõi lịch sử Git, các cột mốc kiến trúc, phân loại thay đổi mã nguồn và định danh bản phát hành đang chạy.',
        mechanism: [
          'Quy Trình Phát Hành: Production chỉ triển khai đúng một commit sau khi CI đạt; tự cập nhật trực tiếp trên máy chủ đã bị tắt.',
          'Phân Tích Git: Thống kê số lượng tính năng mới (feat), sửa lỗi (fix), tối ưu hiệu năng (perf) và ngày phát triển.'
        ],
        metrics: [
          { label: 'Commit Hiện Tại', desc: 'Mã băm Git commit đang chạy thực tế trên máy chủ.' },
          { label: 'Trạng Thái Cập Nhật', desc: 'Báo hiệu khi có bản cập nhật mới hơn trên nhánh main của GitHub.' }
        ],
        playbook: [
          'Dùng trang này để xem trạng thái phiên bản; mọi thay đổi production được áp dụng qua release pipeline.'
        ]
      },
      SETTINGS: {
        id: 'SETTINGS',
        name: 'Cài đặt',
        nameEn: 'Settings & AI',
        icon: Settings,
        category: 'SYSTEM',
        badge: 'Cấu Hình',
        purpose: 'Quản lý API Key nhà cung cấp AI (OpenAI/DeepSeek/Gemini), tinh chỉnh tham số quét, ngưỡng điểm cảnh báo và tùy chọn giao diện/ngôn ngữ.',
        mechanism: [
          'Quản Lý Khóa API AI: Lưu trữ an toàn API Key để kích hoạt Trợ lý AI phân tích thị trường.',
          'Tùy Biến Giao Diện: Chuyển đổi giao diện V1/V2, bật/tắt âm thanh cảnh báo và chuyển đổi 4 ngôn ngữ (VI/EN/ZH/KO).'
        ],
        metrics: [
          { label: 'Nhà Cung Cấp AI', desc: 'Mô hình ngôn ngữ lớn (LLM) được chọn để phân tích thị trường.' },
          { label: 'Ngưỡng Điểm Cảnh Báo', desc: 'Mức điểm phân phối tối thiểu để hệ thống bắt đầu bắn tín hiệu.' }
        ],
        playbook: [
          'Điền API Key Gemini hoặc DeepSeek của bạn để mở khóa toàn bộ tính năng Trợ lý AI thông minh trong Trung tâm Ra quyết định.'
        ]
      },
      FIBO_SHORT: {
        id: 'FIBO_SHORT',
        name: 'Fibo Short (H4/D1)',
        nameEn: 'Confirmed Reversal & Fibo Short',
        icon: GitPullRequest,
        category: 'TRADING',
        badge: 'H4/D1 → H1 Xác nhận',
        purpose: 'Nhánh chiến lược mới: chờ xác nhận đảo chiều cấu trúc trên khung lớn H4/D1, đo Fibonacci tìm vùng hồi quy Golden Pocket (0.500–0.618) và vào lệnh Short theo xu hướng mới khi nến H1 đóng cửa xác nhận.',
        mechanism: [
          'Sóng Đảo Chiều Khung Lớn (H4/D1): Xác định đỉnh Swing High (1.0), nến đỏ đảo chiều và sóng đẩy giảm xuống đáy Impulse Low (0.0).',
          'Thang Giá Fibonacci: Tự động kẻ vùng vào lệnh Golden Pocket (0.500–0.618), cài Stop Loss trên đỉnh Swing High (1.0 + 0.2 ATR), chốt lời TP1 (0.0), TP2 (Ext 1.272), TP3 (Ext 1.618).',
          'Nến Xác Nhận H1 (1+2): Nến H1 đóng đỏ (close < open, price_ret_1h <= 0) + Mẫu hình nến đảo chiều giảm (ĐK 1) + Phá vỡ đáy nến H1 liền trước / gãy mốc Fibo 0.5 (ĐK 2).'
        ],
        metrics: [
          { label: 'Swing High (1.0) → Impulse Low (0.0)', desc: 'Biên độ con sóng đẩy giảm đầu tiên xác nhận đảo chiều trên H4 hoặc D1.' },
          { label: 'Golden Pocket (0.500–0.618)', desc: 'Vùng hồi quy Fibonacci tối ưu để canh vào lệnh Short thuận xu hướng mới.' },
          { label: 'Backtest In-Sample (≤ 2025)', desc: 'Kiểm định lịch sử khóa cứng tới hết 31/12/2025 để giữ nguyên toàn bộ dữ liệu 2026+ làm Out-of-Sample (OOS).' }
        ],
        playbook: [
          'Ưu tiên các mã ở trạng thái "ĐÃ XÁC NHẬN SHORT (H1)" có xác nhận kép (1+2) tại vùng Golden Pocket.',
          'Đặt Stop Loss phía trên đỉnh Swing High (Fibo 1.0 + đệm ATR) và chia chốt lời từng phần tại TP1 (đáy cũ 0.0), TP2 (Ext 1.272) và TP3 (Ext 1.618).'
        ]
      }
    };
  }, [language]);

  if (!isOpen) return null;

  const currentGuide = guides[selectedTab] || guides.DECISION;

  const filteredGuides = Object.values(guides).filter(guide =>
    guide.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    guide.nameEn.toLowerCase().includes(searchTerm.toLowerCase()) ||
    guide.purpose.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-950/90 backdrop-blur-md animate-fade-in">
      <div className="flex flex-col w-full max-w-5xl h-[94vh] max-h-[880px] bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden">
        {/* Modal Top Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 bg-slate-950/90 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="rounded-lg bg-gradient-to-br from-amber-500/20 to-violet-600/20 p-2 text-amber-300 border border-amber-500/30 shadow-inner">
              <Compass className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-sm sm:text-base font-bold text-white flex items-center gap-2">
                <span>{language === 'en' ? 'ĐẢO VÀNG AI RADAR — System Knowledge & User Guide' : language === 'zh' ? 'ĐẢO VÀNG AI RADAR — 用户操作全指南与架构解析' : language === 'ko' ? 'ĐẢO VÀNG AI RADAR — 시스템 가이드 및 지식 센터' : 'ĐẢO VÀNG AI RADAR — CẨM NANG HỆ THỐNG & HƯỚNG DẪN NGƯỜI DÙNG'}</span>
                <span className="rounded bg-amber-500/20 border border-amber-500/40 px-2 py-0.5 text-[10px] font-mono text-amber-300 font-bold">
                  v2.0 Pro
                </span>
              </h2>
              <p className="text-[11px] text-slate-400">
                {language === 'en'
                  ? 'Complete quantitative philosophy, 4-tier engine architecture, models in production, and risk rules'
                  : language === 'zh'
                  ? '系统量化哲学、4层漏斗架构、实盘运行模型、13个Tab全功能与风控军规'
                  : language === 'ko'
                  ? '정량 트레이딩 철학, 4단계 파이프라인 구조, 가동 모델 및 리스크 관리 수칙'
                  : 'Triết lý định lượng, kiến trúc 4 tầng phễu, các mô hình AI/ML đang chạy, hướng dẫn 13 Tab và quy tắc quản trị rủi ro sống còn'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Section Navigation Tabs (Top Bar) */}
        <div className="flex items-center gap-1.5 px-4 py-2 border-b border-slate-800 bg-slate-950/60 overflow-x-auto shrink-0 [&::-webkit-scrollbar]:hidden">
          <button
            type="button"
            onClick={() => setActiveSection('OVERVIEW')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 transition ${
              activeSection === 'OVERVIEW'
                ? 'bg-amber-500 text-slate-950 font-bold shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>{language === 'en' ? '1. Purpose & Architecture' : language === 'zh' ? '1. 目标与4层架构' : language === 'ko' ? '1. 목적 및 4단계 구조' : '1. Mục đích & Kiến trúc 4 Tầng'}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSection('MODELS')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 transition ${
              activeSection === 'MODELS'
                ? 'bg-violet-600 text-white font-bold shadow-md shadow-violet-600/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <Cpu className="w-3.5 h-3.5" />
            <span>{language === 'en' ? '2. Models in Production' : language === 'zh' ? '2. 运行模型解析' : language === 'ko' ? '2. 가동 모델 상세' : '2. Các Mô Hình Đang Chạy'}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSection('TABS')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 transition ${
              activeSection === 'TABS'
                ? 'bg-cyan-600 text-white font-bold shadow-md shadow-cyan-600/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <BookOpen className="w-3.5 h-3.5" />
            <span>{language === 'en' ? '3. 13-Tab Operation Guide' : language === 'zh' ? '3. 13个 Tab 功能详解' : language === 'ko' ? '3. 13개 탭 가이드' : '3. Hướng Dẫn 13 Tab'}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSection('PLAYBOOK')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 transition ${
              activeSection === 'PLAYBOOK'
                ? 'bg-emerald-600 text-white font-bold shadow-md shadow-emerald-600/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <Target className="w-3.5 h-3.5" />
            <span>{language === 'en' ? '4. 4-Step Trading Playbook' : language === 'zh' ? '4. 4步实盘操作流程' : language === 'ko' ? '4. 4단계 실전 플레이북' : '4. Quy Trình Săn Kèo 4 Bước'}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSection('RISK')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 transition ${
              activeSection === 'RISK'
                ? 'bg-rose-600 text-white font-bold shadow-md shadow-rose-600/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <ShieldAlert className="w-3.5 h-3.5" />
            <span>{language === 'en' ? '5. Risk Rules & Notices' : language === 'zh' ? '5. 风险与铁律' : language === 'ko' ? '5. 리스크 수칙' : '5. Lưu Ý & Quản Trị Rủi Ro'}</span>
          </button>
        </div>

        {/* Main Body Content Container */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {/* SECTION 1: OVERVIEW & ARCHITECTURE */}
          {activeSection === 'OVERVIEW' && (
            <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5">
              {/* Core Philosophy Banner */}
              <div className="rounded-xl border border-amber-500/40 bg-gradient-to-br from-amber-950/30 via-slate-900 to-slate-950 p-4 space-y-2">
                <div className="flex items-center gap-2 text-amber-300 font-bold text-sm uppercase">
                  <Flame className="h-5 w-5 text-amber-400 animate-pulse" />
                  <span>Mục Đích Của Ứng Dụng & Triết Lý Cốt Lõi</span>
                </div>
                <p className="text-xs text-slate-200 leading-relaxed">
                  <strong>Đảo Vàng AI Radar</strong> là hệ thống định lượng chuyên biệt được thiết kế để giải quyết bài toán: <strong>Bắt đỉnh phân phối và đi lệnh Short đón đầu các đợt sập giá của coin bơm xả (Pump & Dump Altcoins/Memecoins) trên sàn Binance USDT Futures</strong>.
                </p>
                <div className="p-2.5 rounded-lg bg-slate-950/80 border border-amber-500/20 text-xs font-mono text-amber-200">
                  🎯 <strong>Nguyên lý cốt tử:</strong> &ldquo;Tăng đột biến thì mới sụt đột biến&rdquo;. Hệ thống không đánh đuổi theo sóng tăng bất tận, mà chỉ săn lùng những tài sản đã bơm căng phồng từ +50% đến +300% và bắt đầu có dấu hiệu cạn kiệt thanh khoản, tháo chạy vị thế ngầm của tay to.
                </div>
              </div>

              {/* 4-Tier Funnel Architecture Visual */}
              <div className="space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                  <Cpu className="h-4 w-4 text-violet-400" />
                  <span>Kiến Trúc 4 Tầng Phễu Định Lượng (4-Tier Quant Pipeline)</span>
                </h3>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {/* Tier 1 */}
                  <div className="rounded-xl border border-slate-800 bg-slate-950/80 p-3.5 space-y-2 relative overflow-hidden">
                    <div className="absolute top-0 right-0 px-2 py-0.5 bg-violet-600/30 text-violet-300 font-mono text-[9px] font-bold rounded-bl">TẦNG 1</div>
                    <div className="text-xs font-bold text-violet-300 flex items-center gap-1.5">
                      <BarChart3 className="h-4 w-4 text-violet-400" />
                      <span>Lọc Ứng Viên Bơm Xả</span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Sàng lọc phạm vi Binance Futures theo cấu hình live để lấy nhóm ứng viên có biên độ tăng mạnh và bắt đầu kiệt sức động lượng.
                    </p>
                    <div className="text-[10px] font-mono text-slate-500 border-t border-slate-800/80 pt-1.5">
                      ⚙️ Mô hình: Candidate Filter V2
                    </div>
                  </div>

                  {/* Tier 2 */}
                  <div className="rounded-xl border border-slate-800 bg-slate-950/80 p-3.5 space-y-2 relative overflow-hidden">
                    <div className="absolute top-0 right-0 px-2 py-0.5 bg-amber-600/30 text-amber-300 font-mono text-[9px] font-bold rounded-bl">TẦNG 2</div>
                    <div className="text-xs font-bold text-amber-300 flex items-center gap-1.5">
                      <Zap className="h-4 w-4 text-amber-400" />
                      <span>Kích Hoạt Dòng Lệnh 5m</span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Soi dòng lệnh 5m/15m để bắt thời điểm xả thật; với v2, kế hoạch tham chiếu dùng TP1 -8%, mục tiêu chính -20% và runner -30%.
                    </p>
                    <div className="text-[10px] font-mono text-slate-500 border-t border-slate-800/80 pt-1.5">
                      ⚙️ Mô hình: 2-Tier Climax Engine
                    </div>
                  </div>

                  {/* Tier 3 */}
                  <div className="rounded-xl border border-slate-800 bg-slate-950/80 p-3.5 space-y-2 relative overflow-hidden">
                    <div className="absolute top-0 right-0 px-2 py-0.5 bg-cyan-600/30 text-cyan-300 font-mono text-[9px] font-bold rounded-bl">TẦNG 3</div>
                    <div className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                      <Cpu className="h-4 w-4 text-cyan-400" />
                      <span>Tính Xác Suất Machine Learning</span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Tính xác suất đã hiệu chuẩn từ vector đặc trưng của mô hình đang chọn; độ tin cậy phải được đối chiếu với báo cáo gắn đúng Model ID.
                    </p>
                    <div className="text-[10px] font-mono text-slate-500 border-t border-slate-800/80 pt-1.5">
                      ⚙️ Mô hình: LightGBM + Calibrator
                    </div>
                  </div>

                  {/* Tier 4 */}
                  <div className="rounded-xl border border-slate-800 bg-slate-950/80 p-3.5 space-y-2 relative overflow-hidden">
                    <div className="absolute top-0 right-0 px-2 py-0.5 bg-emerald-600/30 text-emerald-300 font-mono text-[9px] font-bold rounded-bl">TẦNG 4</div>
                    <div className="text-xs font-bold text-emerald-300 flex items-center gap-1.5">
                      <ShieldCheck className="h-4 w-4 text-emerald-400" />
                      <span>Lọc Bẫy & Bối Cảnh Thị Trường</span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Phân loại Market Regime và, khi được cấu hình, dùng Meta-labeling để veto tín hiệu yếu trước khi phát cảnh báo.
                    </p>
                    <div className="text-[10px] font-mono text-slate-500 border-t border-slate-800/80 pt-1.5">
                      ⚙️ Mô hình: Meta-Labeling & Drift
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 2: MODELS IN PRODUCTION */}
          {activeSection === 'MODELS' && (
            <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5">
              <div className="rounded-xl border border-violet-900/60 bg-slate-950/90 p-4 sm:p-5 space-y-5">
                <div className="border-b border-slate-800 pb-3">
                  <h3 className="text-sm font-bold uppercase tracking-wider text-violet-300 flex items-center gap-2">
                    <Cpu className="h-4 w-4 text-violet-400" />
                    <span>Chi Tiết Toàn Bộ 5 Nhóm Mô Hình AI/ML Đang Chạy Thực Tế</span>
                  </h3>
                  <p className="text-xs text-slate-400 mt-1">
                    Hệ thống phối hợp 5 nhóm thuật toán định lượng theo chuỗi đường ống (pipeline) khép kín, từ lọc ứng viên, bắt nhịp nến 5m đến kiểm duyệt xác suất và kiểm soát rủi ro vĩ mô.
                  </p>
                </div>

                <div className="space-y-4 text-xs">
                  {/* Model 1 */}
                  <div className="rounded-xl border border-violet-800/80 bg-slate-900/80 p-4 space-y-3 shadow-inner">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-violet-900/40 pb-2">
                      <div className="flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-violet-600/30 text-violet-300 font-bold font-mono text-xs">01</div>
                        <span className="font-black text-violet-300 text-sm">Two-Tier Climax Engine (v2.0)</span>
                      </div>
                      <span className="rounded-full bg-violet-950 border border-violet-600 px-2.5 py-0.5 text-[9px] font-bold text-violet-200">CHAMPION SCORING ENGINE</span>
                    </div>

                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="space-y-1.5 bg-slate-950/60 p-3 rounded-lg border border-slate-800/80">
                        <div className="font-bold text-amber-300 flex items-center gap-1.5 text-xs">
                          <Zap className="h-3.5 w-3.5 text-amber-400" />
                          <span>Tầng 1 (Bộ lọc khung lớn 1h/4h/24h) &rarr; Đang sẵn sàng</span>
                        </div>
                        <p className="text-slate-300 text-[11px] leading-relaxed">
                          • <strong>Biên độ bơm:</strong> Tăng trưởng tích lũy từ <strong>+50% đến +300%</strong> trong 1–5 ngày.<br/>
                          • <strong>Khoảng cách tới đỉnh:</strong> Giá cách đỉnh cao nhất &le; 30% (bỏ qua coin đã xả xong).<br/>
                          • <strong>Quét râu thanh khoản:</strong> Phát hiện nến rút râu quét đỉnh cũ (Liquidity Sweep) và phân kỳ cạn kiệt khối lượng.
                        </p>
                      </div>

                      <div className="space-y-1.5 bg-slate-950/60 p-3 rounded-lg border border-slate-800/80">
                        <div className="font-bold text-emerald-300 flex items-center gap-1.5 text-xs">
                          <Target className="h-3.5 w-3.5 text-emerald-400" />
                          <span>Tầng 2 (Kích hoạt thời gian thực 5m/15m) &rarr; Đã kích hoạt</span>
                        </div>
                        <p className="text-slate-300 text-[11px] leading-relaxed">
                          • <strong>OI Unwind (Tháo chạy vị thế):</strong> Open Interest sụt giảm &ge; 3% khi giá chững lại.<br/>
                          • <strong>Taker Sell Burst:</strong> Tỷ lệ bán chủ động vọt lên <strong>&ge; 55% - 58%</strong>.<br/>
                          • <strong>Bẫy Funding Rate:</strong> Phí funding âm sâu hoặc dương vọt đỉnh (Z-score &ge; 2.0).
                        </p>
                      </div>
                    </div>

                    <div className="bg-violet-950/30 p-3 rounded-lg border border-violet-900/60 space-y-1.5">
                      <div className="font-bold text-violet-200 text-xs flex items-center gap-1">
                        <Scale className="h-3.5 w-3.5 text-violet-400" />
                        <span>Công Thức Trade Setup & Quản Trị Vốn Tự Động:</span>
                      </div>
                      <div className="grid gap-2 sm:grid-cols-3 text-[11px] text-slate-300 font-mono">
                        <div>• <strong>Stop Loss (SL):</strong> Đỉnh nến gần nhất + 0.5% (TB 2.24%, Max 4%)</div>
                        <div>• <strong>TP1:</strong> -4.0% (Chốt 50%, dời SL hòa vốn)</div>
                        <div>• <strong>TP2 / TP3:</strong> -8.0% (Chốt 30%) / -12.0% (Gồng 20%)</div>
                      </div>
                    </div>

                    <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/80 space-y-1.5">
                      <div className="font-bold text-violet-300 text-xs flex items-center gap-1.5">
                        <Compass className="h-3.5 w-3.5 text-violet-400" />
                        <span>Vị Trí Ứng Dụng Trong Giao Diện:</span>
                      </div>
                      <div className="grid gap-1.5 sm:grid-cols-2 text-[11px] text-slate-300">
                        <div>• <strong>Tab Vào lệnh:</strong> Tính bảng Trade Setup (Entry, SL, TP1-3, R:R) & điểm Phân phối.</div>
                        <div>• <strong>Tab Tín hiệu:</strong> Gán huy hiệu Đang sẵn sàng / Đã kích hoạt và bật âm thanh cảnh báo.</div>
                        <div>• <strong>Tab Top coin xả:</strong> Tuyển chọn danh sách Top 30 ứng viên kiệt sức động lượng.</div>
                        <div>• <strong>Telegram Bot:</strong> Tự động đóng gói và bắn tin nhắn cảnh báo kèm mốc SL/TP.</div>
                      </div>
                    </div>

                    <div className="text-[11px] text-slate-400 flex flex-wrap items-center gap-4 pt-1">
                      <span className="text-emerald-400 font-bold">✓ Kết quả: đọc từ báo cáo gắn Model ID</span>
                      <span className="text-emerald-400 font-bold">✓ Phạm vi: đúng cấu hình và kỳ đánh giá</span>
                      <span className="text-cyan-400 font-bold">✓ R:R: tính riêng cho từng setup</span>
                      <span className="text-amber-400 font-bold">✓ Lead time: chỉ báo khi đủ mẫu</span>
                    </div>
                  </div>

                  {/* Model 2 */}
                  <div className="rounded-xl border border-amber-800/80 bg-slate-900/80 p-4 space-y-3 shadow-inner">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-900/40 pb-2">
                      <div className="flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-amber-600/30 text-amber-300 font-bold font-mono text-xs">02</div>
                        <span className="font-black text-amber-300 text-sm">Frozen Machine Learning Models (LightGBM)</span>
                      </div>
                      <span className="rounded-full bg-amber-950 border border-amber-600 px-2.5 py-0.5 text-[9px] font-bold text-amber-200">VERSIONED CHECKPOINT</span>
                    </div>

                    <p className="text-slate-300 leading-relaxed text-xs">
                      Production nạp một gói mô hình LightGBM đóng băng theo <strong>Model ID và checksum</strong>. Walk-Forward Validation kết hợp Embargo Window giúp giảm rủi ro nhìn trước; bằng chứng hiện hành phải đi cùng đúng gói mô hình.
                    </p>

                    <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800/80 space-y-2">
                      <div className="font-bold text-amber-300 text-xs">
                        📊 Vector 25 Đặc Trưng Vi Cấu Trúc Đầu Vào (Input Features 25 chiều):
                      </div>
                      <div className="grid gap-2 sm:grid-cols-2 text-[10px] text-slate-300 leading-relaxed font-mono">
                        <div>• <strong>Động lượng & Biên độ giá:</strong> price_ret_5m, price_ret_1h, price_ret_4h, price_ret_24h, price_volatility_24h, distance_from_high_24h, momentum_deceleration_4h, fake_breakout_1h.</div>
                        <div>• <strong>Hợp đồng mở & Dòng tiền:</strong> oi_change_1h, oi_change_4h, oi_change_24h, taker_buy_ratio, volume_percentile_24h.</div>
                        <div>• <strong>Funding & Tâm lý đám đông:</strong> funding_rate_raw, funding_percentile_7d/30d, funding_zscore_30d, funding_change_8h/24h, funding_persistence_7d.</div>
                        <div>• <strong>Tương quan Cá Mập vs Nhỏ Lẻ:</strong> global_ls_ratio, top_ls_ratio, retail_top_spread, spread_trend_1h/4h.</div>
                      </div>
                    </div>

                    <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/80 space-y-1.5">
                      <div className="font-bold text-amber-300 text-xs flex items-center gap-1.5">
                        <Compass className="h-3.5 w-3.5 text-amber-400" />
                        <span>Vị Trí Ứng Dụng Trong Giao Diện:</span>
                      </div>
                      <div className="grid gap-1.5 sm:grid-cols-2 text-[11px] text-slate-300">
                        <div>• <strong>Tab Vào lệnh:</strong> Hiển thị xác suất/điểm rủi ro và các thành phần đóng góp có trọng số.</div>
                        <div>• <strong>Tab Tín hiệu:</strong> Sắp xếp danh sách tín hiệu theo xác suất cao nhất (Probability Sort).</div>
                        <div>• <strong>Tab Forward Test:</strong> Đánh giá hiệu năng ngoài mẫu (OOS) của 5 checkpoint mô hình.</div>
                        <div>• <strong>Tab Kiểm định:</strong> Cung cấp ma trận nhầm lẫn (Confusion Matrix TP, FP, TN, FN).</div>
                      </div>
                    </div>
                  </div>

                  {/* Model 3 */}
                  <div className="rounded-xl border border-cyan-800/80 bg-slate-900/80 p-4 space-y-2.5 shadow-inner">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cyan-900/40 pb-2">
                      <div className="flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-cyan-600/30 text-cyan-300 font-bold font-mono text-xs">03</div>
                        <span className="font-black text-cyan-300 text-sm">Isotonic Probability Calibrator</span>
                      </div>
                      <span className="rounded-full bg-cyan-950 border border-cyan-600 px-2.5 py-0.5 text-[9px] font-bold text-cyan-200">HIỆU CHUẨN XÁC SUẤT TOÁN HỌC</span>
                    </div>

                    <p className="text-slate-300 leading-relaxed text-xs">
                      Điểm số thô của mô hình cây quyết định thường có độ lệch biên. Bộ hiệu chuẩn <strong>Isotonic Regression</strong> thiết lập hàm ánh xạ đơn điệu phi tham số; Brier Score và ECE phải được đọc từ báo cáo của đúng Model ID và kỳ đánh giá.
                    </p>
                    <div className="text-[11px] text-cyan-300 font-mono bg-slate-950/60 p-2 rounded border border-cyan-900/40">
                      💡 <strong>Cách đọc:</strong> Xác suất là ước lượng của mô hình, không phải cam kết. Hãy kiểm tra đường cong hiệu chuẩn, cỡ mẫu và khoảng bất định của phiên bản đang chạy.
                    </div>

                    <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/80 space-y-1.5">
                      <div className="font-bold text-cyan-300 text-xs flex items-center gap-1.5">
                        <Compass className="h-3.5 w-3.5 text-cyan-400" />
                        <span>Vị Trí Ứng Dụng Trong Giao Diện:</span>
                      </div>
                      <div className="grid gap-1.5 sm:grid-cols-2 text-[11px] text-slate-300">
                        <div>• <strong>Tab Vào lệnh & Tín hiệu:</strong> Hiển thị huy hiệu Xác suất % chuẩn hóa trên từng coin.</div>
                        <div>• <strong>Tab Kiểm định:</strong> Vẽ đường cong hiệu chuẩn Brier Score & độ tin cậy AI.</div>
                      </div>
                    </div>
                  </div>

                  {/* Model 4 */}
                  <div className="rounded-xl border border-emerald-800/80 bg-slate-900/80 p-4 space-y-2.5 shadow-inner">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-emerald-900/40 pb-2">
                      <div className="flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-emerald-600/30 text-emerald-300 font-bold font-mono text-xs">04</div>
                        <span className="font-black text-emerald-300 text-sm">HistGradientBoosting Meta-Labeling Model</span>
                      </div>
                      <span className="rounded-full bg-emerald-950 border border-emerald-600 px-2.5 py-0.5 text-[9px] font-bold text-emerald-200">BỘ LỌC TÍN HIỆU BẪY (LỚP 2)</span>
                    </div>

                    <p className="text-slate-300 leading-relaxed text-xs">
                      Dựa trên công trình nghiên cứu kinh điển của GS. Marcos López de Prado (<em>Advances in Financial Machine Learning</em>). Mô hình Meta-labeling hoạt động như một quan tòa phúc thẩm độc lập: Khi Tầng 2 & 3 phát tín hiệu Short, mô hình này sẽ phân tích các sai số tiềm ẩn để quyết định xem có cho phép bấm nút hay không (1: Cho phép, 0: Bác bỏ).
                    </p>
                    <div className="text-[11px] text-emerald-300 font-mono bg-slate-950/60 p-2 rounded border border-emerald-900/40">
                      🛡️ <strong>Vai trò bảo vệ:</strong> Có thể veto tín hiệu yếu hoặc bẫy tăng tiếp; mức hiệu quả được đánh giá riêng theo từng phiên bản và giai đoạn thị trường.
                    </div>

                    <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/80 space-y-1.5">
                      <div className="font-bold text-emerald-300 text-xs flex items-center gap-1.5">
                        <Compass className="h-3.5 w-3.5 text-emerald-400" />
                        <span>Vị Trí Ứng Dụng Trong Giao Diện & Backend:</span>
                      </div>
                      <div className="grid gap-1.5 sm:grid-cols-2 text-[11px] text-slate-300">
                        <div>• <strong>Tab Thị trường (Alpha Lab):</strong> Hiển thị trạng thái Meta-Labeling do API cung cấp.</div>
                        <div>• <strong>Scanner Daemon:</strong> Tự động chặn (VETO) tín hiệu giả trước khi bắn Telegram.</div>
                      </div>
                    </div>
                  </div>

                  {/* Model 5 */}
                  <div className="rounded-xl border border-rose-800/80 bg-slate-900/80 p-4 space-y-2.5 shadow-inner">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rose-900/40 pb-2">
                      <div className="flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-rose-600/30 text-rose-300 font-bold font-mono text-xs">05</div>
                        <span className="font-black text-rose-300 text-sm">Market Regime Classifier & Drift Guardian</span>
                      </div>
                      <span className="rounded-full bg-rose-950 border border-rose-600 px-2.5 py-0.5 text-[9px] font-bold text-rose-200">GIÁM SÁT VĨ MÔ & SUY HAO ALPHA</span>
                    </div>

                    <p className="text-slate-300 leading-relaxed text-xs">
                      • <strong>Market Regime:</strong> Kết hợp chỉ số ADX và Bollinger Band Width để phân loại trạng thái thị trường (`TRENDING_BEAR`, `TRENDING_BULL`, `CHOPPY`, `RANGE`).<br/>
                      • <strong>Drift Guardian:</strong> Liên tục đo lường chỉ số ổn định dữ liệu (Population Stability Index - PSI) trên cửa sổ trượt 7 ngày để phát hiện sớm hiện tượng suy giảm hiệu quả của các đặc trưng (Alpha Decay) và tự động bật cảnh báo cho người vận hành.
                    </p>

                    <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/80 space-y-1.5">
                      <div className="font-bold text-rose-300 text-xs flex items-center gap-1.5">
                        <Compass className="h-3.5 w-3.5 text-rose-400" />
                        <span>Vị Trí Ứng Dụng Trong Giao Diện:</span>
                      </div>
                      <div className="grid gap-1.5 sm:grid-cols-2 text-[11px] text-slate-300">
                        <div>• <strong>Tab Thị trường:</strong> Hiển thị thẻ Market Regime (ADX, BB Width) & Drift Guardian (PSI).</div>
                        <div>• <strong>Tab Top coin xả & Tín hiệu:</strong> Gắn nhãn 5 loại bất thường (Funding, OI, Volume).</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
          {/* SECTION 3: 13-TAB OPERATION GUIDE */}
          {activeSection === 'TABS' && (
            <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
              {/* Left Sidebar: Tab List Selector */}
              <div className="w-full md:w-64 bg-slate-950/60 border-b md:border-b-0 md:border-r border-slate-800 flex flex-col shrink-0">
                {/* Search Input */}
                <div className="p-2 border-b border-slate-800/80">
                  <div className="relative">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-slate-400" />
                    <input
                      type="text"
                      placeholder="Tìm kiếm Tab hoặc chỉ số..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700/80 rounded-lg pl-7 pr-2 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-500"
                    />
                  </div>
                </div>

                {/* Tab Selector List */}
                <div className="flex-1 overflow-y-auto p-1.5 space-y-1">
                  {filteredGuides.map((guide) => {
                    const isSelected = selectedTab === guide.id;
                    const IconComponent = guide.icon;
                    return (
                      <button
                        key={guide.id}
                        onClick={() => setSelectedTab(guide.id)}
                        className={`w-full flex items-center justify-between p-2 rounded-lg text-left transition ${
                          isSelected
                            ? 'bg-violet-950/80 border border-violet-600/80 text-white shadow-sm'
                            : 'text-slate-300 hover:bg-slate-800/60 hover:text-white border border-transparent'
                        }`}
                      >
                        <div className="flex items-center gap-2 overflow-hidden">
                          <div className={`p-1 rounded-md ${isSelected ? 'bg-violet-600 text-white' : 'bg-slate-800 text-slate-400'}`}>
                            <IconComponent className="h-3 w-3" />
                          </div>
                          <div className="truncate">
                            <div className="text-xs font-bold truncate">
                              {guide.name}
                            </div>
                            <div className="text-[9px] text-slate-400 font-mono">
                              {guide.id}
                            </div>
                          </div>
                        </div>
                        {isSelected && <ChevronRight className="h-3 w-3 text-violet-400 shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Right Content Area: Detailed Guide for Selected Tab */}
              <div className="flex-1 overflow-y-auto p-3 sm:p-5 space-y-4 bg-slate-900/40">
                {/* Header of Selected Tab */}
                <div className="flex flex-wrap items-center justify-between gap-2 p-3 rounded-xl border border-violet-900/60 bg-gradient-to-r from-violet-950/40 via-slate-900 to-slate-950">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 rounded-xl bg-violet-600/20 border border-violet-500/40 text-violet-300">
                      {React.createElement(currentGuide.icon, { className: 'h-5 w-5' })}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm sm:text-base font-black text-white">{currentGuide.name}</h3>
                        <span className="px-1.5 py-0.2 rounded bg-violet-900/80 border border-violet-700 text-[9px] font-mono text-violet-200 font-bold">
                          {currentGuide.id}
                        </span>
                        {currentGuide.badge && (
                          <span className="px-2 py-0.2 rounded-full bg-emerald-950/80 border border-emerald-700 text-[8px] text-emerald-300 font-semibold">
                            {currentGuide.badge}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Section 1: Purpose */}
                <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3.5 space-y-1.5">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center gap-1.5">
                    <Target className="h-3.5 w-3.5 text-violet-400" />
                    <span>1. Mục Đích & Giá Trị Cốt Lõi</span>
                  </h4>
                  <p className="text-xs text-slate-300 leading-relaxed pl-4">
                    {currentGuide.purpose}
                  </p>
                </div>

                {/* Section 2: Mechanism */}
                <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3.5 space-y-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center gap-1.5">
                    <Cpu className="h-3.5 w-3.5 text-amber-400" />
                    <span>2. Cơ Chế Vận Hành & Thuật Toán Định Lượng</span>
                  </h4>
                  <div className="space-y-1.5 pl-4">
                    {currentGuide.mechanism.map((item, idx) => (
                      <div key={idx} className="flex items-start gap-2 text-xs text-slate-300 leading-relaxed">
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" />
                        <span>{item}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Section 3: Metrics */}
                <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3.5 space-y-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center gap-1.5">
                    <BarChart3 className="h-3.5 w-3.5 text-cyan-400" />
                    <span>3. Giải Thích Thông Số & Chỉ Số Quan Trọng</span>
                  </h4>
                  <div className="grid gap-2 sm:grid-cols-2 pl-4">
                    {currentGuide.metrics.map((m, idx) => (
                      <div key={idx} className="rounded-lg border border-slate-800/80 bg-slate-900/60 p-2.5 space-y-1">
                        <div className="text-xs font-bold text-cyan-300 font-mono">{m.label}</div>
                        <div className="text-[11px] text-slate-300 leading-normal">{m.desc}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Section 4: Playbook */}
                <div className="rounded-xl border border-emerald-900/50 bg-gradient-to-br from-emerald-950/20 via-slate-950 to-slate-950 p-3.5 space-y-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-emerald-300 flex items-center gap-1.5">
                    <Lightbulb className="h-3.5 w-3.5 text-yellow-400" />
                    <span>4. Chiến Lược Sử Dụng Thực Chiến Hiệu Quả</span>
                  </h4>
                  <div className="space-y-1.5 pl-4">
                    {currentGuide.playbook.map((step, idx) => (
                      <div key={idx} className="flex items-start gap-2 text-xs text-slate-200 leading-relaxed">
                        <div className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-600/30 text-[10px] font-bold text-emerald-400 border border-emerald-500/40 mt-0.5">
                          {idx + 1}
                        </div>
                        <span>{step}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 4: 4-STEP TRADING PLAYBOOK */}
          {activeSection === 'PLAYBOOK' && (
            <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
              <div className="rounded-xl border border-emerald-900/60 bg-slate-950/80 p-4 space-y-4">
                <h3 className="text-xs font-bold uppercase tracking-wider text-emerald-300 flex items-center gap-2">
                  <Target className="h-4 w-4 text-emerald-400" />
                  <span>Quy Trình 4 Bước Săn Kèo Thực Chiến Chuẩn Định Lượng</span>
                </h3>

                <div className="grid gap-3 md:grid-cols-2">
                  {/* Step 1 */}
                  <div className="rounded-lg border border-slate-800 bg-slate-900/80 p-3.5 space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="h-5 w-5 rounded-full bg-violet-600 text-white flex items-center justify-center font-bold text-xs">1</span>
                      <span className="font-bold text-slate-200 text-xs uppercase">Bước 1: Quét Tín Hiệu (Tab Tín hiệu / Telegram)</span>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed pl-7">
                      Xem danh sách coin cảnh báo. Ưu tiên các coin có nhãn <strong>Đã kích hoạt</strong> (đang bắt đầu xả) hoặc <strong>Rủi ro nóng</strong> với xác suất $\ge 70\%$. Bấm vào coin để chuyển sang màn hình <em>Vào lệnh</em>.
                    </p>
                  </div>

                  {/* Step 2 */}
                  <div className="rounded-lg border border-slate-800 bg-slate-900/80 p-3.5 space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="h-5 w-5 rounded-full bg-amber-600 text-white flex items-center justify-center font-bold text-xs">2</span>
                      <span className="font-bold text-slate-200 text-xs uppercase">Bước 2: Thẩm Định Buồng Lái (Tab Vào lệnh)</span>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed pl-7">
                      Kiểm tra nến 15m/5m, đối chiếu <strong>Taker Sell Ratio $\ge 55\%$</strong> và <strong>Open Interest giảm</strong>. Đọc thẻ <em>Trade Setup</em> để lấy giá Entry, SL và 3 mức TP chuẩn xác.
                    </p>
                  </div>

                  {/* Step 3 */}
                  <div className="rounded-lg border border-slate-800 bg-slate-900/80 p-3.5 space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="h-5 w-5 rounded-full bg-cyan-600 text-white flex items-center justify-center font-bold text-xs">3</span>
                      <span className="font-bold text-slate-200 text-xs uppercase">Bước 3: Đi Lệnh Kỷ Luật (Vào Lệnh & Cài SL)</span>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed pl-7">
                      Vào lệnh Short trong vùng Entry, đặt <strong>Stop Loss bắt buộc</strong> ngay trên đỉnh nến gần nhất (trung bình 2.2%, tối đa 4%). Tuyệt đối không thả SL hoặc gồng lỗ.
                    </p>
                  </div>

                  {/* Step 4 */}
                  <div className="rounded-lg border border-slate-800 bg-slate-900/80 p-3.5 space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="h-5 w-5 rounded-full bg-emerald-600 text-white flex items-center justify-center font-bold text-xs">4</span>
                      <span className="font-bold text-slate-200 text-xs uppercase">Bước 4: Quản Trị Vị Thế & Chốt Lời (Tab Vị thế)</span>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed pl-7">
                      Bấm &ldquo;Thêm vào Vị thế&rdquo; để theo dõi PnL trực tiếp. Với contract v2, khi giá chạm <strong>TP1 (-8%)</strong>: chốt 50% và <strong>dời SL về điểm hòa vốn</strong>; giữ 30% tới mục tiêu chính -20% và 20% runner tới -30%.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 5: RISK & NOTICES */}
          {activeSection === 'RISK' && (
            <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
              <div className="rounded-xl border border-rose-900/60 bg-slate-950/80 p-4 space-y-4">
                <h3 className="text-xs font-bold uppercase tracking-wider text-rose-300 flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4 text-rose-400" />
                  <span>5 Nguyên Tắc Quản Trị Rủi Ro & Lưu Ý Sống Còn</span>
                </h3>

                <div className="space-y-3 text-xs">
                  <div className="p-3 rounded-lg bg-rose-950/30 border border-rose-800/60 text-rose-200 space-y-1">
                    <div className="font-bold text-rose-300 flex items-center gap-1.5">
                      <AlertTriangle className="h-4 w-4 text-rose-400" />
                      <span>1. Đòn Bẩy Khuyến Nghị & Tỷ Lệ Đi Vốn (Position Sizing)</span>
                    </div>
                    <p className="text-slate-300 leading-relaxed pl-5">
                      Coin bơm xả (Altcoins/Memecoins) có biên độ giật rất mạnh. Khuyến nghị đòn bẩy tối đa <strong>$3x - 5x$ (tối đa không quá $10x$)</strong>. Mỗi lệnh chỉ nên chịu rủi ro tối đa <strong>$1\% - 2\%$ tổng tài khoản</strong> nếu dính Stop Loss.
                    </p>
                  </div>

                  <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 text-slate-200 space-y-1">
                    <div className="font-bold text-amber-300 flex items-center gap-1.5">
                      <CheckCircle2 className="h-4 w-4 text-amber-400" />
                      <span>2. Kỷ Luật Cắt Lỗ — Không Bao Giờ Thả Stop Loss</span>
                    </div>
                    <p className="text-slate-300 leading-relaxed pl-5">
                      Nếu giá tăng vượt ngưỡng MAE cho phép (&gt; 4%) và cắn SL, hãy chấp nhận cắt lỗ ngay lập tức. Các đợt Short Squeeze điên cuồng có thể x3 x5 tài sản trong vài giờ, việc gồng lỗ Short là con đường nhanh nhất dẫn đến cháy tài khoản.
                    </p>
                  </div>

                  <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 text-slate-200 space-y-1">
                    <div className="font-bold text-cyan-300 flex items-center gap-1.5">
                      <Info className="h-4 w-4 text-cyan-400" />
                      <span>3. Kiểm Tra Bối Cảnh Thị Trường (Market Regime)</span>
                    </div>
                    <p className="text-slate-300 leading-relaxed pl-5">
                      Khi Bitcoin đang trong pha tăng điên cuồng (Bull Frenzy / ADX &gt; 40), các lệnh Short Altcoin sẽ chịu áp lực thanh lý rất lớn. Hãy ưu tiên đi lệnh mạnh khi Tab <em>Thị Trường</em> báo trạng thái `TRENDING_BEAR` hoặc `CHOPPY`.
                    </p>
                  </div>

                  <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 text-slate-200 space-y-1">
                    <div className="font-bold text-slate-400 flex items-center gap-1.5">
                      <Scale className="h-4 w-4 text-slate-400" />
                      <span>4. Tuyên Bố Miễn Trừ Trách Nhiệm (Disclaimer)</span>
                    </div>
                    <p className="text-slate-400 leading-relaxed pl-5 text-[11px]">
                      Đảo Vàng AI Radar cung cấp các chỉ số, xác suất và phân tích định lượng độc lập nhằm hỗ trợ người dùng nâng cao chất lượng quyết định. Đây không phải là lời khuyên đầu tư tài chính hay ủy thác giao dịch. Mọi quyết định đi lệnh và quản trị vốn đều thuộc toàn quyền trách nhiệm của người sử dụng.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-2.5 border-t border-slate-800 bg-slate-950/90 text-[11px] text-slate-400 shrink-0">
          <div className="flex items-center gap-1.5">
            <Lightbulb className="h-3.5 w-3.5 text-yellow-400" />
            <span>Mẹo: Bạn có thể chọn bất kỳ Tab nào ở cột bên trái hoặc chuyển chuyên mục ở thanh điều hướng trên cùng để tra cứu.</span>
          </div>
          <button
            onClick={onClose}
            className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-white rounded-md text-xs font-medium transition"
          >
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
};
