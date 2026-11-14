import type { Language } from './translations';

type LangTuple = readonly [en: string, zh: string, ko: string];

/**
 * Exact & Substring phrase dictionary for localizing Vietnamese UI labels and
 * backend-generated Vietnamese diagnostic strings (`branch_title_vi`, `reason_vi`,
 * `explanation_vi`, `label_vi`, `m6_rejection_reasons_vi`, `ExecutionDashboard`,
 * `FiboShortWorkspace`, `ModelsDocTab`, `TabHelpModal`) into EN / ZH / KO.
 *
 * Loaded lazily only when `language !== 'vi'`, keeping the main entry bundle size untouched.
 */
const PHRASE_MAP: ReadonlyArray<readonly [vi: string, LangTuple]> = [
  // FiboShortWorkspace — Header & Mode Switcher
  [
    'Xác Nhận Đảo Chiều & Short Theo Xu Hướng Mới (Fibonacci H4/D1 → H1 · v4.0.21)',
    [
      'Confirmed Reversal & New Downtrend Short (Fibonacci H4/D1 → H1 · v4.0.21)',
      '确认反转与顺势做空引擎 (斐波那契 H4/D1 → H1 · v4.0.21)',
      '추세 반전 확인 및 신규 하락 추세 숏 (피보나치 H4/D1 → H1 · v4.0.21)',
    ],
  ],
  [
    'Xác Nhận Đảo Chiều & Short Theo Xu Hướng Mới (Fibonacci H4/D1 → H1)',
    [
      'Confirmed Reversal & New Downtrend Short (Fibonacci H4/D1 → H1)',
      '确认反转与顺势做空引擎 (斐波那契 H4/D1 → H1)',
      '추세 반전 확인 및 신규 하락 추세 숏 (피보나치 H4/D1 → H1)',
    ],
  ],
  [
    '4 Nhân Tố Trực Giao (F1–F4) · Chỉ Báo Telegram Khi Đủ 4 Cổng Sniper · Định Cỡ Vốn Theo Rủi Ro 0.5% NAV',
    [
      '4 Orthogonal Factors (F1–F4) · Telegram Alerts Only When All 4 Sniper Gates Pass · 0.5% NAV Risk Sizing',
      '四维正交因子 (F1–F4) · 仅当通过全部 4 道 Sniper 门控时推送 Telegram · 按 0.5% NAV 风险定仓',
      '4대 직교 팩터 (F1–F4) · 4단계 스나이퍼 조건 충족 시 텔레그램 알림 · 0.5% NAV 리스크 비중 산출',
    ],
  ],
  [
    'Tín Hiệu Live (5 Phút)',
    ['Live Signals (5m)', '实时信号 (5分钟)', '실시간 시그널 (5분)'],
  ],
  [
    'Đối Chiếu Shadow (Cũ vs v4.0.21)',
    ['Shadow Comparison (Legacy vs v4.0.21)', 'Shadow 实时对照 (旧版 vs v4.0.21)', '섀도우 비교 (구버전 vs v4.0.21)'],
  ],
  [
    'Kiểm Toán 6 Năm (2020–2025)',
    ['6-Year Audit (2020–2025)', '6 年历史审计 (2020–2025)', '6년 백테스트 감사 (2020–2025)'],
  ],
  [
    'Paper OOS v1 (12 Tài Khoản)',
    ['Paper OOS v1 (12 Accounts)', 'Paper OOS v1 (12 独立账户)', 'Paper OOS v1 (12개 계좌)'],
  ],
  [
    'Quét Fibo Ngay',
    ['Scan Fibo Now', '立即扫描 Fibo', '즉시 Fibo 스캔'],
  ],
  [
    'Đang Quét...',
    ['Scanning...', '扫描中...', '스캔 중...'],
  ],
  [
    'Mở Biểu Đồ & Lệnh',
    ['Open Chart & Order Setup', '打开图表与交易计划', '차트 및 주문 설정 열기'],
  ],
  [
    'Xem Biểu Đồ',
    ['View Chart', '查看图表', '차트 보기'],
  ],
  [
    'Đủ Chuẩn Vào Lệnh (Sniper)',
    ['Actionable Sniper Setups', '符合入场标准 (Sniper)', '진입 가능 (Sniper)'],
  ],
  [
    'Đã Xác Nhận H1 (Fired)',
    ['H1 Confirmed (Fired)', 'H1 已确认触发 (Fired)', 'H1 컨펌 완료 (Fired)'],
  ],
  [
    'Đang Trong Vùng Fibo (Armed)',
    ['In Fibo Zone (Armed)', '进入斐波那契区 (Armed)', '피보나치 구간 진입 (Armed)'],
  ],
  [
    'Đang Chờ Hồi Quy (Watching)',
    ['Watching Pullback', '等待反弹回踩 (Watching)', '되돌림 대기 중 (Watching)'],
  ],
  [
    'Tất Cả Tín Hiệu',
    ['All Signals', '全部信号', '전체 시그널'],
  ],
  [
    'Chỉ Kèo Đủ Chuẩn (Sniper)',
    ['Qualified Sniper Only', '仅显示达标 Sniper', '스나이퍼 조건 충족만'],
  ],
  [
    'Mọi Khung',
    ['All Timeframes', '全部周期', '모든 시간프레임'],
  ],
  [
    'Mọi Chính Sách',
    ['All Policies', '全部策略', '모든 정책'],
  ],

  // Shadow Comparison View
  [
    'Đối Chiếu Song Song Thời Gian Thực: Hệ Thống Cũ (Baseline) vs. Hệ Thống Nâng Cấp v4.0.21',
    [
      'Real-Time Parallel Shadow Comparison: Legacy Baseline (M1 Raw) vs. Upgraded v4.0.21 System',
      '实时并行 Shadow 对照：旧版基准系统 (M1 Raw) vs. 升级版 v4.0.21 系统',
      '실시간 병렬 섀도우 비교: 구버전(M1 Raw) vs 업그레이드 v4.0.21 시스템',
    ],
  ],
  [
    'Hệ Thống Cũ (M1 Raw · Vốn 20% · SL 1.0) vs. Hệ Thống Nâng Cấp (v4.0.21 · SL 0.886 Ratchet · Risk 0.5% NAV)',
    [
      'Legacy (M1 Raw · 20% Size · SL 1.0) vs. Upgraded (v4.0.21 · SL 0.886 Ratchet · 0.5% NAV Risk)',
      '旧版 (M1 Raw · 20% 固定仓位 · SL 1.0) vs. 升级版 (v4.0.21 · SL 0.886 移动保本 · 0.5% NAV 风险)',
      '구버전 (M1 Raw · 20% 고정비중 · SL 1.0) vs 업그레이드 (v4.0.21 · SL 0.886 본절이동 · 0.5% NAV 리스크)',
    ],
  ],
  [
    'Tổng Tín Hiệu M1 Đã Quét',
    ['Total M1 Signals Evaluated', '累计评估 M1 信号总数', '총 M1 평가 시그널'],
  ],
  [
    'Đã Chặn Nhiễu (Sniper)',
    ['Noise Filtered Out (Sniper)', '已拦截噪音信号 (Sniper)', '노이즈 필터링 차단 (Sniper)'],
  ],
  [
    'Hiệu Suất TB/Lệnh & Δ NAV (M6 vs Cũ)',
    ['Avg Return/Trade & Δ NAV (M6 vs Legacy)', '单笔平均收益与 Δ NAV (M6 vs 旧版)', '평균 수익/건 및 Δ NAV (M6 vs 구버전)'],
  ],
  [
    '1. Bảng Đối Chiếu Hiệu Suất 5 Nhánh Shadow Trực Tiếp (Live Scanner 5 Phút · Khởi Điểm NAV = 100.00)',
    [
      '1. 5-Track Live Shadow Performance Matrix (5m Live Scanner · Initial NAV = 100.00)',
      '1. 五路实时 Shadow 绩效对照矩阵 (5分钟实时扫描 · 初始 NAV = 100.00)',
      '1. 5개 트랙 실시간 섀도우 성과 비교표 (5분 라이브 스캐너 · 시작 NAV = 100.00)',
    ],
  ],
  [
    '2. Sổ Cái Đối Chiếu Từng Lệnh Thời Gian Thực (Signal-by-Signal Shadow Audit: Hệ Thống Cũ vs. v4.0.21)',
    [
      '2. Real-Time Signal-by-Signal Shadow Audit Ledger (Legacy M1 vs. v4.0.21)',
      '2. 逐笔信号实时 Shadow 审计台账 (旧版系统 vs. v4.0.21)',
      '2. 실시간 개별 시그널 섀도우 감사 원장 (구버전 vs v4.0.21)',
    ],
  ],
  [
    '3. Đối Chiếu Daemon Paper OOS v1 (24/7): Baseline Đi Vốn Cố Định 20% (`reference_m6_fixed`) vs. 5 Chính Sách `v4.0.21`',
    [
      '3. 24/7 Paper OOS v1 Daemon Comparison: Fixed 20% Baseline (`reference_m6_fixed`) vs. 5 `v4.0.21` Policies',
      '3. 24/7 Paper OOS v1 守护进程对照：20% 固定仓位基准 (`reference_m6_fixed`) vs. 5 项 `v4.0.21` 策略',
      '3. 24/7 Paper OOS v1 데몬 비교: 20% 고정 비중(`reference_m6_fixed`) vs 5대 `v4.0.21` 정책',
    ],
  ],
  [
    '4. Đối Chiếu Song Song Nhánh Chính (Main Scanner): Champion `pump_filter_v1` (Cũ) vs. Challenger `candidate_filter_v2` (Mới)',
    [
      '4. Main Scanner Parallel Filter Audit: Champion `pump_filter_v1` (Legacy) vs. Challenger `candidate_filter_v2` (New)',
      '4. 主扫描器并行过滤器审计：Champion `pump_filter_v1` (旧) vs. Challenger `candidate_filter_v2` (新)',
      '4. 메인 스캐너 병렬 필터 비교: Champion `pump_filter_v1` (구) vs Challenger `candidate_filter_v2` (신)',
    ],
  ],
  [
    'Hệ Thống Cũ · M1 Raw (Vốn Cố Định 20% · SL Đỉnh 1.0)',
    [
      'Legacy System · M1 Raw (Fixed 20% NAV · Swing High SL 1.0)',
      '旧版系统 · M1 Raw (固定 20% NAV · 前高 SL 1.0)',
      '구버전 시스템 · M1 Raw (고정 20% NAV · 고점 SL 1.0)',
    ],
  ],
  [
    'v4.0.21 · M6 Expanded (SL 0.886 Ratchet · Risk 0.5% NAV)',
    [
      'v4.0.21 · M6 Expanded (SL 0.886 Ratchet · 0.5% NAV Risk)',
      'v4.0.21 · M6 扩展版 (SL 0.886 移动保本 · 0.5% NAV 风险)',
      'v4.0.21 · M6 확장형 (SL 0.886 본절이동 · 0.5% NAV 리스크)',
    ],
  ],
  [
    'v4.0.21 · M6 Sniper (Phá Đáy H1 + KER ≥ 0.50 · Risk 0.5%)',
    [
      'v4.0.21 · M6 Sniper (H1 Low Break + KER ≥ 0.50 · 0.5% Risk)',
      'v4.0.21 · M6 Sniper (H1 破前低 + KER ≥ 0.50 · 0.5% 风险)',
      'v4.0.21 · M6 스나이퍼 (H1 저점 돌파 + KER ≥ 0.50 · 0.5% 리스크)',
    ],
  ],
  [
    'v4.0.21 · Elite Sniper (Carver PST + Phá Đáy H1 · Risk 0.5%)',
    [
      'v4.0.21 · Elite Sniper (Carver PST + H1 Low Break · 0.5% Risk)',
      'v4.0.21 · Elite Sniper (Carver PST + H1 破前低 · 0.5% 风险)',
      'v4.0.21 · 엘리트 스나이퍼 (Carver PST + H1 저점 돌파 · 0.5% 리스크)',
    ],
  ],
  [
    'v4.0.21 · Sniper RR≥1 · 24h (Top Return/MaxDD 5.74x)',
    [
      'v4.0.21 · Sniper RR≥1 · 24h (Top Return/MaxDD 5.74x)',
      'v4.0.21 · Sniper RR≥1 · 24小时 (最佳收益回撤比 5.74x)',
      'v4.0.21 · 스나이퍼 RR≥1 · 24시간 (최고 수익/MDD 5.74x)',
    ],
  ],
  [
    'Nhánh Hệ Thống (Shadow Track)',
    ['Shadow Track', 'Shadow 对照分支', '섀도우 트랙'],
  ],
  [
    'Tín Hiệu M1',
    ['M1 Signals', 'M1 信号数', 'M1 시그널'],
  ],
  [
    'Nhận Lệnh',
    ['Accepted', '采纳信号', '수락 건수'],
  ],
  [
    'Chặn Nhiễu',
    ['Filtered Out', '拦截噪音', '노이즈 차단'],
  ],
  [
    'Đang Mở / Đóng',
    ['Open / Closed', '持仓中 / 已平仓', '진행 / 종료'],
  ],
  [
    'TB Lợi Nhuận/Lệnh',
    ['Avg Return / Trade', '单笔平均收益', '건당 평균 수익'],
  ],
  [
    'Tác Động NAV',
    ['Cumulative NAV Impact', '累计 NAV 贡献', '누적 NAV 영향'],
  ],
  [
    'Δ Cải Thiện vs Cũ',
    ['Δ vs Legacy', 'Δ 对比旧版', '구버전 대비 Δ'],
  ],
  [
    'Mốc gốc (0.000%)',
    ['Baseline (0.000%)', '基准线 (0.000%)', '기준선 (0.000%)'],
  ],
  [
    'ĐÃ CHẶN NHIỄU (FILTERED OUT)',
    ['NOISE BLOCKED (FILTERED OUT)', '已拦截噪音 (FILTERED OUT)', '노이즈 차단됨 (FILTERED OUT)'],
  ],
  [
    '0.000% (An toàn)',
    ['0.000% (Capital Protected)', '0.000% (资金安全)', '0.000% (원금 보호)'],
  ],

  // Paper OOS v1 View
  [
    '12 Tài Khoản Paper OOS Độc Lập (6 Chính Sách × 2 Kịch Bản Phí · Vốn Quy Đổi $10,000.00 / TK · NAV Gốc = 100)',
    [
      '12 Independent Paper OOS Accounts (6 Policies × 2 Fee Scenarios · $10,000.00 Equiv / Account · Base NAV = 100)',
      '12 个独立 Paper OOS 模拟账户 (6 项策略 × 2 种费率场景 · 折合 $10,000.00 / 账户 · 初始 NAV = 100)',
      '12개 독립 Paper OOS 모의계좌 (6대 정책 × 2가지 수수료 시나리오 · 계좌당 $10,000.00 환산 · 기준 NAV = 100)',
    ],
  ],
  [
    'Bấm vào từng dòng tài khoản để lọc riêng lệnh đang vào của tài khoản đó',
    [
      'Click any account row to filter open and closed trades for that specific account',
      '点击任意账户行即可单独筛选该账户的持仓与历史交易',
      '계좌 행을 클릭하면 해당 계좌의 진행/종료 내역만 필터링됩니다',
    ],
  ],
  [
    'Tiến Độ Nghiên Cứu',
    ['OOS Study Progress', '样本外验证进度', 'OOS 연구 진행률'],
  ],
  [
    'Vị Thế Đang Mở',
    ['Open Positions', '当前持仓数', '진행 중인 포지션'],
  ],
  [
    'Lệnh Đã Đóng',
    ['Closed Trades', '已平仓笔数', '종료된 거래'],
  ],
  [
    'Tài Khoản / Chính Sách',
    ['Account / Policy', '账户 / 策略', '계좌 / 정책'],
  ],
  [
    'Kịch Bản Phí',
    ['Cost Scenario', '费率场景', '수수료 시나리오'],
  ],
  [
    'Tài Sản ($10k) / NAV',
    ['Equity ($10k) / NAV', '账户权益 ($10k) / NAV', '자산 ($10k) / NAV'],
  ],
  [
    'Đang Mở',
    ['Open', '持仓中', '진행 중'],
  ],
  [
    'Đã Khớp / Bị Lọc',
    ['Accepted / Filtered', '已成交 / 已过滤', '체결 / 필터링'],
  ],
  [
    'Đã Đóng',
    ['Closed', '已平仓', '종료됨'],
  ],
  [
    'Phí + Trượt + Funding',
    ['Fee + Slippage + Funding', '手续费 + 滑点 + 资金费', '수수료 + 슬리피지 + 펀딩'],
  ],
  [
    'Đối soát đầy đủ phí khớp lệnh, độ trượt giá và Funding thực tế trên Binance USD-M',
    [
      'Fully reconciled with Binance USD-M execution fees, slippage, and realized funding settlements',
      '已完整核对币安 USD-M 实盘手续费、滑点与真实资金费率结算',
      '바이낸스 USD-M 체결 수수료, 슬리피지 및 실제 펀딩비 정산 완벽 대사',
    ],
  ],
  [
    'Thời Gian Vào → Đóng (UTC)',
    ['Entry → Exit Time (UTC)', '开仓 → 平仓时间 (UTC)', '진입 → 종료 시간 (UTC)'],
  ],
  [
    'Giá Vào → Giá Đóng',
    ['Entry → Exit Price', '开仓价 → 平仓价', '진입가 → 종료가'],
  ],
  [
    'Lý Do Thoát Lệnh',
    ['Exit Reason', '平仓原因', '청산 사유'],
  ],
  [
    'PnL Ròng (% NAV)',
    ['Net PnL (% NAV)', '净盈亏 (% NAV)', '순손익 (% NAV)'],
  ],

  // ExecutionDashboard (Tab 3 Live 10k / Real Binance)
  [
    'Tài khoản Paper Test & Giao dịch',
    ['10,000 USDT Paper Simulation & Execution', '10,000 USDT 模拟交易与执行引擎', '10,000 USDT 모의투자 및 실행 엔진'],
  ],
  [
    'Tài khoản & giao dịch',
    ['Live Account & Execution', '实盘账户与执行引擎', '실계좌 및 주문 실행'],
  ],
  [
    'MÔ PHỎNG',
    ['SIMULATION', '模拟盘', '시뮬레이션'],
  ],
  [
    'TIỀN THẬT',
    ['LIVE REAL MONEY', '实盘资金', '실전 계좌'],
  ],
  [
    'Tổng tài sản',
    ['Total Equity', '账户总权益', '총 자산 (Equity)'],
  ],
  [
    'Số dư khả dụng',
    ['Available Balance', '可用余额', '가용 잔고'],
  ],
  [
    'Lãi/lỗ chưa chốt',
    ['Unrealized PnL', '未实现盈亏', '미실현 손익'],
  ],
  [
    'Giảm từ đỉnh',
    ['Drawdown from Peak', '最高点回撤', '고점 대비 낙폭 (DD)'],
  ],
  [
    'Bao gồm lãi/lỗ chưa chốt',
    ['Includes unrealized PnL', '包含未实现盈亏', '미실현 손익 포함'],
  ],
  [
    'Đường tài sản',
    ['Equity Curve', '资金净值曲线', '자산 곡선 (Equity Curve)'],
  ],
  [
    'Từ tài khoản mô phỏng',
    ['From Paper Simulation Account', '来自模拟交易账户', '모의투자 계좌 기준'],
  ],
  [
    'Tiến trình vận hành',
    ['Operational Gate Progress', '实盘准入验证进度', '운영 검증 진행률'],
  ],
  [
    '1. Quan sát',
    ['1. Observation', '1. 观察期', '1. 관찰 단계'],
  ],
  [
    '2. Demo',
    ['2. Demo', '2. 模拟盘', '2. 데모'],
  ],
  [
    '3. Tiền thật',
    ['3. Live Capital', '3. 实盘资金', '3. 실전 매매'],
  ],
  [
    'Thời gian có bản ghi',
    ['Observed Duration', '已记录观察天数', '관찰 기록 일수'],
  ],
  [
    'Sự kiện độc lập',
    ['Independent Events', '独立信号事件', '독립 시그널 이벤트'],
  ],
  [
    'Cửa sổ thời gian',
    ['Time Windows', '时间窗口', '시간 윈도우'],
  ],
  [
    'Chưa đủ điều kiện tiền thật',
    ['Live Capital Gate Not Yet Met', '尚未满足实盘资金准入条件', '실전 매매 전환 조건 미충족'],
  ],
  [
    'CHẾ ĐỘ KHÁCH · CHỈ XEM',
    ['GUEST MODE · READ-ONLY', '访客模式 · 仅限查看', '게스트 모드 · 읽기 전용'],
  ],
  [
    'Admin điều khiển',
    ['Admin Controls', '管理员控制', '관리자 제어'],
  ],
  [
    'Dừng mở mới',
    ['Pause New Entries', '暂停开立新仓', '신규 진입 일시정지'],
  ],
  [
    'Bật lại mở mới',
    ['Resume Entries', '恢复开立新仓', '신규 진입 재개'],
  ],
  [
    'Chưa có vị thế được bot quản lý.',
    ['No active bot-managed positions.', '当前暂无机器人管理的持仓。', '현재 봇이 관리 중인 활성 포지션이 없습니다.'],
  ],
  [
    'Chưa có giao dịch đã kết thúc.',
    ['No closed trades yet.', '暂无已平仓交易记录。', '아직 종료된 거래 내역이 없습니다.'],
  ],
  [
    'Chưa ghi nhận tín hiệu giao dịch.',
    ['No execution signals recorded yet.', '暂无交易信号记录。', '기록된 실행 시그널이 없습니다.'],
  ],
  [
    'Yêu cầu điều khiển',
    ['Control Commands', '控制指令记录', '제어 명령 내역'],
  ],
  [
    'Nhật ký vận hành',
    ['Operational Activity Log', '运行活动日志', '운영 활동 로그'],
  ],
  [
    'Làm mới',
    ['Refresh', '刷新', '새로고침'],
  ],
];

const REGEX_PATTERNS: ReadonlyArray<{
  re: RegExp;
  replace: (match: RegExpExecArray, lang: Exclude<Language, 'vi'>) => string;
}> = [
  {
    re: /^(\d+)\s+mở\s*\/\s*(\d+)\s+đóng$/,
    replace: (m, l) =>
      l === 'en' ? `${m[1]} open / ${m[2]} closed` : l === 'zh' ? `${m[1]} 持仓 / ${m[2]} 平仓` : `${m[1]} 진행 / ${m[2]} 종료`,
  },
  {
    re: /^(\d+)\s*\/\s*(\d+)\s+lệnh$/,
    replace: (m, l) =>
      l === 'en' ? `${m[1]} / ${m[2]} trades` : l === 'zh' ? `${m[1]} / ${m[2]} 笔` : `${m[1]} / ${m[2]} 건`,
  },
  {
    re: /^(\d+)\s+lệnh$/,
    replace: (m, l) => (l === 'en' ? `${m[1]} trades` : l === 'zh' ? `${m[1]} 笔` : `${m[1]} 건`),
  },
  {
    re: /^(\d+)\s*\/\s*(\d+)\s+tuần$/,
    replace: (m, l) =>
      l === 'en' ? `${m[1]} / ${m[2]} weeks` : l === 'zh' ? `${m[1]} / ${m[2]} 周` : `${m[1]} / ${m[2]} 주`,
  },
  {
    re: /^Cập nhật lúc:\s*(.+)$/,
    replace: (m, l) =>
      l === 'en' ? `Updated: ${m[1]}` : l === 'zh' ? `更新时间：${m[1]}` : `업데이트: ${m[1]}`,
  },
  {
    re: /^Biến động giá:\s*(.+)$/,
    replace: (m, l) =>
      l === 'en' ? `Price move: ${m[1]}` : l === 'zh' ? `价格变动：${m[1]}` : `가격 변동: ${m[1]}`,
  },
  {
    re: /^Vốn\s+([\d.]+%\s*NAV)$/,
    replace: (m, l) =>
      l === 'en' ? `Size ${m[1]}` : l === 'zh' ? `仓位 ${m[1]}` : `비중 ${m[1]}`,
  },
  {
    re: /^NHẬN LỆNH\s*\((.+)\)$/,
    replace: (m, l) =>
      l === 'en' ? `ACCEPTED (${m[1]})` : l === 'zh' ? `已采纳 (${m[1]})` : `수락됨 (${m[1]})`,
  },
  {
    re: /^Lý do chặn:\s*(.+)$/,
    replace: (m, l) =>
      l === 'en' ? `Filtered reason: ${m[1]}` : l === 'zh' ? `拦截原因：${m[1]}` : `차단 사유: ${m[1]}`,
  },
  {
    re: /^Vị thế\s*\((\d+)\)$/,
    replace: (m, l) =>
      l === 'en' ? `Positions (${m[1]})` : l === 'zh' ? `持仓 (${m[1]})` : `포지션 (${m[1]})`,
  },
  {
    re: /^Lịch sử\s*\((\d+)\)$/,
    replace: (m, l) =>
      l === 'en' ? `History (${m[1]})` : l === 'zh' ? `历史 (${m[1]})` : `이력 (${m[1]})`,
  },
];

const SUBSTRING_REPLACEMENTS: ReadonlyArray<readonly [vi: string, LangTuple]> = [
  ['Biên độ nhịp sập', ['Impulse drop', '下跌波幅', '하락 파동 폭']],
  ['Nhịp sập thiếu dứt khoát', ['Choppy impulse drop', '下跌波不够干脆', '하락 파동 효율 부족']],
  ['Nhịp hồi vượt Fibo 0.786', ['Pullback exceeded Fibo 0.786', '反弹超过 Fibo 0.786', '되돌림 Fibo 0.786 초과']],
  ['Chưa phá đáy H1 liền trước', ['H1 prev low not broken', '未跌破前一根 H1 低点', '이전 H1 저점 미돌파']],
  ['Paper OOS v1 đang chạy', ['Paper OOS v1 running', 'Paper OOS v1 运行中', 'Paper OOS v1 실행 중']],
  ['Nhật ký SQLite toàn vẹn', ['SQLite journal verified', 'SQLite 日志完整性已验证', 'SQLite 저널 무결성 확인']],
  ['12 tài khoản độc lập (6 chính sách × 2 kịch bản phí) · Không gửi lệnh thật.', ['12 isolated accounts (6 policies × 2 fee tiers) · No live orders sent.', '12 个独立账户 (6 项策略 × 2 种费率) · 不发送实盘订单。', '12개 독립 계좌 (6대 정책 × 2가지 수수료) · 실주문 미전송.']],
  ['Mở lệnh mới: Theo điều kiện chiến lược', ['New Entries: Active per Strategy Rules', '开立新仓：按策略条件自动执行', '신규 진입: 전략 조건에 따라 활성']],
  ['Mở lệnh mới: Đã dừng', ['New Entries: Paused', '开立新仓：已暂停', '신규 진입: 일시정지됨']],
  ['Số dư ví:', ['Wallet balance:', '钱包余额：', '지갑 잔고:']],
  ['Đỉnh tài sản:', ['Equity peak:', '历史最高权益：', '자산 최고점:']],
  ['vị thế bot', ['bot positions', '个机器人持仓', '개 봇 포지션']],
];

interface AnnotatedText extends Text {
  __origViText?: string;
  __lastLang?: Language;
}

const EXACT_LOOKUP: Record<string, LangTuple> = {};
for (const [vi, tuple] of PHRASE_MAP) {
  EXACT_LOOKUP[vi] = tuple;
}

function translateString(raw: string, lang: Exclude<Language, 'vi'>): string {
  const trimmed = raw.trim();
  if (!trimmed) return raw;
  const idx = lang === 'en' ? 0 : lang === 'zh' ? 1 : 2;

  const exact = EXACT_LOOKUP[trimmed];
  if (exact) {
    return raw.replace(trimmed, exact[idx]);
  }

  for (const pat of REGEX_PATTERNS) {
    const m = pat.re.exec(trimmed);
    if (m) {
      return raw.replace(trimmed, pat.replace(m, lang));
    }
  }

  let out = raw;
  for (const [viSub, tuple] of SUBSTRING_REPLACEMENTS) {
    if (out.includes(viSub)) {
      out = out.split(viSub).join(tuple[idx]);
    }
  }
  return out;
}

export function applyDomLocalization(root: Node, lang: Language): void {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode() as AnnotatedText | null;
  while (node) {
    const parentTag = node.parentElement?.tagName;
    if (parentTag !== 'SCRIPT' && parentTag !== 'STYLE' && parentTag !== 'TEXTAREA') {
      const currentVal = node.nodeValue || '';
      if (lang === 'vi') {
        if (node.__origViText !== undefined && currentVal !== node.__origViText) {
          node.nodeValue = node.__origViText;
        }
        node.__lastLang = 'vi';
      } else {
        if (node.__origViText === undefined || node.__lastLang === 'vi') {
          node.__origViText = currentVal;
        }
        const sourceText = node.__origViText;
        const translated = translateString(sourceText, lang);
        if (translated !== currentVal) {
          node.nodeValue = translated;
        }
        node.__lastLang = lang;
      }
    }
    node = walker.nextNode() as AnnotatedText | null;
  }
}
