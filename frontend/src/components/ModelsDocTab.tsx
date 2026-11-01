import React, { useState, useEffect, useMemo } from 'react';
import { 
  Brain, Shield, BarChart3, Network, Settings, Check, X,
  FileText, Download, Copy, CheckCheck, BookOpen, Sparkles,
  ChevronRight, Calendar, Users, Database, Loader2
} from 'lucide-react';
import { MarkdownRenderer } from './DecisionCenter/MarkdownRenderer';

interface ResearchPaper {
  id: string;
  code: string;
  title: string;
  title_en?: string;
  date: string;
  category: string;
  tags: string[];
  key_metric: string;
  sample_size: string;
  badge: string;
  badge_color: 'emerald' | 'amber' | 'cyan' | 'purple' | 'blue' | 'slate';
  abstract: string;
  content: string;
  file_size_bytes?: number;
  evidence_scope?: 'historical_research' | string;
}

const FALLBACK_REPORTS: ResearchPaper[] = [];

export const ModelsDocTab: React.FC = () => {
  const [subTab, setSubTab] = useState<'OVERVIEW' | 'RESEARCH'>('RESEARCH');
  const [reports, setReports] = useState<ResearchPaper[]>(FALLBACK_REPORTS);
  const [selectedReportId, setSelectedReportId] = useState<string>('');
  const [selectedTag, setSelectedTag] = useState<string>('ALL');
  const [sortOrder, setSortOrder] = useState<'NEWEST' | 'OLDEST'>('NEWEST');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [copied, setCopied] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Fetch reports list from backend API
  useEffect(() => {
    let isMounted = true;
    const fetchReports = async () => {
      try {
        setIsLoading(true);
        const res = await fetch('/api/research/reports');
        if (res.ok) {
          const data = await res.json();
          if (data.reports && data.reports.length > 0 && isMounted) {
            setReports(data.reports);
            if (!data.reports.some((r: ResearchPaper) => r.id === selectedReportId)) {
              setSelectedReportId(data.reports[0].id);
            }
          }
        }
      } catch (err) {
        console.warn('Failed to fetch research reports API, using fallback:', err);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };
    fetchReports();
    return () => { isMounted = false; };
  }, []);

  // Filter tags
  const allTags = useMemo(() => {
    const set = new Set<string>();
    reports.forEach(r => r.tags?.forEach(t => set.add(t)));
    return ['ALL', ...Array.from(set)];
  }, [reports]);

  // Filtered reports
  const filteredReports = useMemo(() => {
    const filtered = reports.filter(r => {
      const matchTag = selectedTag === 'ALL' || r.tags?.includes(selectedTag);
      const matchSearch = !searchQuery.trim() || 
        r.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        r.abstract.toLowerCase().includes(searchQuery.toLowerCase()) ||
        r.code.toLowerCase().includes(searchQuery.toLowerCase());
      return matchTag && matchSearch;
    });

    return filtered.sort((a, b) => {
      const dateA = new Date(a.date).getTime();
      const dateB = new Date(b.date).getTime();
      return sortOrder === 'NEWEST' ? dateB - dateA : dateA - dateB;
    });
  }, [reports, selectedTag, searchQuery, sortOrder]);

  const selectedReport = useMemo(() => {
    return reports.find(r => r.id === selectedReportId) || reports[0] || FALLBACK_REPORTS[0];
  }, [reports, selectedReportId]);

  const handleCopyMarkdown = () => {
    if (!selectedReport?.content) return;
    navigator.clipboard.writeText(selectedReport.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadMarkdown = () => {
    if (!selectedReport?.content) return;
    const blob = new Blob([selectedReport.content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${selectedReport.id || 'research_report'}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const getBadgeColor = (color: string) => {
    switch (color) {
      case 'emerald': return 'bg-emerald-950/80 text-emerald-400 border-emerald-800/60';
      case 'amber': return 'bg-amber-950/80 text-amber-400 border-amber-800/60';
      case 'cyan': return 'bg-cyan-950/80 text-cyan-400 border-cyan-800/60';
      case 'purple': return 'bg-purple-950/80 text-purple-400 border-purple-800/60';
      case 'blue': return 'bg-blue-950/80 text-blue-400 border-blue-800/60';
      default: return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-slate-950 text-slate-300">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-800 px-4 py-3 bg-slate-900/60 backdrop-blur shrink-0 gap-3">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-gradient-to-br from-amber-500/20 to-cyan-500/20 border border-amber-500/30 rounded-lg">
            <Brain className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider">Tài Liệu Models & Thư Viện Nghiên Cứu Lịch Sử</h2>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800/50 font-mono flex items-center gap-1">
                {isLoading && <Loader2 className="w-2.5 h-2.5 animate-spin text-cyan-400" />}
                <span>{reports.length} Papers</span>
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Kiến trúc thuật toán và báo cáo nghiên cứu lưu trữ; số liệu lịch sử không đại diện cho model production hiện tại.
            </p>
          </div>
        </div>

        {/* Sub-tab Navigation */}
        <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg p-0.5 self-start sm:self-auto">
          <button
            onClick={() => setSubTab('RESEARCH')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
              subTab === 'RESEARCH'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <BookOpen className="w-3.5 h-3.5" />
            <span>Thư Viện Nghiên Cứu ({reports.length})</span>
          </button>
          <button
            onClick={() => setSubTab('OVERVIEW')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
              subTab === 'OVERVIEW'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Network className="w-3.5 h-3.5" />
            <span>Kiến Trúc & Bối Cảnh Lịch Sử</span>
          </button>
        </div>
      </div>

      <div className="shrink-0 border-b border-amber-800/60 bg-amber-950/35 px-4 py-2 text-[11px] leading-relaxed text-amber-200">
        <strong>Lưu ý phạm vi:</strong> Các Precision, ECE, ROI và trạng thái trong thư viện này là ảnh chụp nghiên cứu lịch sử. Bản production chỉ được xác định bằng Model ID, checksum và báo cáo forward-test gắn với đúng phiên bản đang chạy.
      </div>

      {/* Main Content Area */}
      {subTab === 'RESEARCH' ? (
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
          {/* Left Sidebar: Report List */}
          <div className="w-full md:w-80 lg:w-96 border-r border-slate-800 flex flex-col bg-slate-900/40 shrink-0 h-1/2 md:h-full">
            {/* Filter & Search */}
            <div className="p-3 border-b border-slate-800 space-y-2 bg-slate-900/60">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Tìm kiếm nghiên cứu..."
                  className="flex-1 min-w-0 bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-[11px] text-slate-200 placeholder-slate-500 focus:outline-none focus:border-amber-500/50"
                />
                <select
                  value={sortOrder}
                  onChange={(e) => setSortOrder(e.target.value as 'NEWEST' | 'OLDEST')}
                  className="bg-slate-950 border border-slate-800 rounded px-2 py-1.5 text-[11px] text-slate-300 focus:outline-none focus:border-amber-500/50 cursor-pointer shrink-0"
                >
                  <option value="NEWEST">Mới nhất</option>
                  <option value="OLDEST">Cũ nhất</option>
                </select>
              </div>
              <div className="flex flex-wrap gap-1 max-h-16 overflow-y-auto no-scrollbar pt-1">
                {allTags.map(tag => (
                  <button
                    key={tag}
                    onClick={() => setSelectedTag(tag)}
                    className={`px-1.5 py-0.5 rounded text-[10px] font-mono transition-colors ${
                      selectedTag === tag
                        ? 'bg-amber-500/30 text-amber-300 border border-amber-500/50'
                        : 'bg-slate-950 text-slate-400 border border-slate-800 hover:text-slate-200'
                    }`}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>

            {/* Reports List */}
            <div className="flex-1 overflow-y-auto divide-y divide-slate-800/40 p-2 space-y-1.5">
              {filteredReports.map((report) => {
                const isSelected = report.id === selectedReportId;
                return (
                  <div
                    key={report.id}
                    onClick={() => setSelectedReportId(report.id)}
                    className={`p-2.5 rounded-lg border cursor-pointer transition-all ${
                      isSelected
                        ? 'bg-slate-800/90 border-amber-500/50 shadow-md ring-1 ring-amber-500/20'
                        : 'bg-slate-950/60 border-slate-800/60 hover:bg-slate-850 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1 mb-1">
                      <span className="text-[10px] font-mono text-cyan-400 font-semibold">{report.code}</span>
                      <span className={`text-[9px] px-1.5 py-0.2 rounded border font-medium ${getBadgeColor(report.badge_color)}`}>
                        {report.badge}
                      </span>
                    </div>
                    <h3 className={`text-xs font-semibold line-clamp-2 mb-1.5 ${isSelected ? 'text-amber-300' : 'text-slate-200'}`}>
                      {report.title}
                    </h3>
                    <p className="text-[10px] text-slate-400 line-clamp-2 mb-2 leading-relaxed">
                      {report.abstract}
                    </p>
                    <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-800/40">
                      <div className="flex items-center gap-1 font-mono text-emerald-400 font-medium">
                        <span>{report.key_metric}</span>
                      </div>
                      <span className="text-slate-400 text-[9px]">{report.date}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right Main Area: Full Paper Markdown Reader */}
          <div className="flex-1 flex flex-col h-1/2 md:h-full bg-slate-950 overflow-hidden">
            {/* Paper Toolbar */}
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800 bg-slate-900/70 shrink-0">
              <div className="flex items-center gap-2 overflow-hidden">
                <FileText className="w-4 h-4 text-amber-400 shrink-0" />
                <span className="text-xs font-bold text-slate-200 truncate">{selectedReport?.title}</span>
                <span className="text-[10px] font-mono text-slate-400 shrink-0 hidden sm:inline">({selectedReport?.code})</span>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <button
                  onClick={handleCopyMarkdown}
                  className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px] border border-slate-700 transition-colors"
                  title="Sao chép Markdown vào bộ nhớ tạm"
                >
                  {copied ? <CheckCheck className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copied ? 'Đã chép' : 'Chép MD'}</span>
                </button>
                <button
                  onClick={handleDownloadMarkdown}
                  className="flex items-center gap-1 px-2.5 py-1 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 text-[11px] border border-amber-500/40 transition-colors"
                  title="Tải về file tài liệu Markdown (.md)"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Tải .md</span>
                </button>
              </div>
            </div>

            {/* Paper Header Metadata Card */}
            <div className="bg-slate-900/40 border-b border-slate-800 px-4 py-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] shrink-0">
              <div className="flex items-center gap-2">
                <Calendar className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                <div>
                  <div className="text-[9px] text-slate-400 uppercase">Ngày công bố</div>
                  <div className="font-mono text-slate-200">{selectedReport?.date}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Database className="w-3.5 h-3.5 text-purple-400 shrink-0" />
                <div>
                  <div className="text-[9px] text-slate-400 uppercase">Quy mô mẫu</div>
                  <div className="text-slate-200 font-medium truncate">{selectedReport?.sample_size}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Sparkles className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                <div>
                  <div className="text-[9px] text-slate-400 uppercase">Kết quả cốt lõi</div>
                  <div className="text-emerald-400 font-bold truncate">{selectedReport?.key_metric}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Users className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                <div>
                  <div className="text-[9px] text-slate-400 uppercase">Phân loại</div>
                  <div className="font-mono text-cyan-300">{selectedReport?.category}</div>
                </div>
              </div>
            </div>

            {/* Document Content */}
            <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
              <MarkdownRenderer content={selectedReport?.content || ''} />
            </div>
          </div>
        </div>
      ) : (
        /* Overview Sub-tab */
        <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
          {/* Official 2-Tier Production Architecture Banner */}
          <div className="bg-slate-900 border border-emerald-500/30 rounded-lg p-4">
            <div className="flex items-center space-x-2 mb-3">
              <Shield className="w-4 h-4 text-emerald-400" />
              <h3 className="text-xs font-bold text-emerald-300 uppercase">
                Kiến Trúc Production Chính Thức 2 Tầng: Fibo Short v4.0.21 + Radar Sớm V3.1
              </h3>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-[11px]">
              <div className="bg-slate-950 p-3 rounded border border-emerald-900/50">
                <div className="font-semibold text-emerald-400 mb-1">
                  Tầng 2 (Chính thức): Fibo Short v4.0.21
                </div>
                <p className="text-slate-300 leading-relaxed">
                  Đảm nhiệm toàn bộ <strong>cảnh báo Telegram chính thức</strong> và tab <strong>FIBO_SHORT</strong>. Chỉ phát lệnh trên rổ <code>rolling_pit_top50</code> khi đã có sóng xả <code>KER &ge; 0.50</code>, hồi nông Fibonacci và <strong>phá đáy H1</strong> (2 chính sách chuẩn: <code>elite_sniper_risk</code> +26.19%/6 năm &amp; <code>sniper_rr1_horizon24</code> +21.46%/2024–2025) kèm SL <code>0.886</code> và định cỡ <code>0.5% NAV</code>.
                </p>
              </div>
              <div className="bg-slate-950 p-3 rounded border border-sky-900/50">
                <div className="font-semibold text-sky-400 mb-1">
                  Tầng 1 (Radar Sớm): V3.1 Săn Đỉnh (UI-Only)
                </div>
                <p className="text-slate-300 leading-relaxed">
                  Chạy mỗi 5 phút trên tab <strong>RADAR / WATCHLIST</strong> (<code>shadow_telegram_enabled: false</code>) để phát hiện sớm các Altcoin đang bơm quá nhiệt &amp; cạn kiệt Funding. <strong>Không dùng để Short trực tiếp ngược sóng bơm</strong> khi chưa có xác nhận gãy cấu trúc H1 từ Fibo Short.
                </p>
              </div>
              <div className="bg-slate-950 p-3 rounded border border-amber-900/50">
                <div className="font-semibold text-amber-400 mb-1">
                  Tầng 3 (Auto-Trading): Khóa An Toàn (Paper OOS)
                </div>
                <p className="text-slate-300 leading-relaxed">
                  <code>ExecutionEngine</code> đang khóa cứng <code>live_activated: false</code>. Hệ thống vận hành 12 tài khoản <code>paper_oos_v1</code> thời gian thực để kiểm chứng trượt giá thực tế (&le; 12.5 bps/fill với lệnh Limit Post-Only ở TP1/TP2) trước khi cấp quyền đánh tự động.
                </p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Section 1: Kiến Trúc Hệ Thống */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center space-x-2 mb-4">
                <Network className="w-4 h-4 text-cyan-400" />
                <h3 className="text-xs font-bold text-slate-200 uppercase">1. Kiến Trúc Đánh Giá 3 Động Cơ</h3>
              </div>
              <div className="space-y-4 text-[11px]">
                <div className="bg-slate-950 p-3 rounded border border-slate-800/50">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold text-amber-400">V1 Heuristic Engine (Giải thích trực quan)</span>
                    <span className="text-[9px] px-1.5 py-0.5 bg-slate-800 rounded text-slate-400">distribution_scorer.py</span>
                  </div>
                  <p className="text-slate-400 mb-2">Hệ thống trọng số 8 thành phần để người dùng quan sát lý do thị trường:</p>
                  <ul className="list-disc pl-4 space-y-1 text-slate-300">
                    <li><span className="text-cyan-300">20%</span> Khúc xạ giá/khối lượng (Price-Volume Divergence)</li>
                    <li><span className="text-cyan-300">15%</span> Đột biến Funding Rate (Funding Spike)</li>
                    <li><span className="text-cyan-300">15%</span> Cạn kiệt xung lượng (Momentum Exhaustion)</li>
                    <li><span className="text-cyan-300">15%</span> Bối cảnh thị trường BTC (BTC Context Filter)</li>
                    <li><span className="text-slate-400">35%</span> Orderbook, Taker Sell, Open Interest, Fake Breakout</li>
                  </ul>
                </div>
                
                <div className="bg-slate-950 p-3 rounded border border-slate-800/50">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold text-emerald-400">V2 Two-Tier Climax</span>
                  </div>
                  <p className="text-slate-400 mb-1">Xác nhận tín hiệu qua 2 khung thời gian:</p>
                  <div className="flex flex-col space-y-1">
                    <div className="flex items-center space-x-2"><div className="w-1.5 h-1.5 rounded-full bg-slate-500"></div><span><strong className="text-slate-300">HTF (High Timeframe):</strong> Trạng thái Armed / Normal</span></div>
                    <div className="flex items-center space-x-2"><div className="w-1.5 h-1.5 rounded-full bg-cyan-500"></div><span><strong className="text-slate-300">LTF (Low Timeframe):</strong> Kích hoạt Fired / Watch / Standby</span></div>
                  </div>
                </div>

                <div className="bg-slate-950 p-3 rounded border border-slate-800/50">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold text-purple-400">Frozen ML Pipeline (Bộ lọc quyết định bắn tín hiệu)</span>
                  </div>
                  <p className="text-slate-400">Pipeline học máy cô lập trạng thái với LightGBM / Logistic Regression và dùng <strong>Isotonic Calibration</strong>. Chất lượng hiệu chuẩn phải đọc từ báo cáo gắn với từng Model ID.</p>
                </div>
              </div>
            </div>

                <div className="bg-slate-950 p-3 rounded border border-slate-800/50">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold text-rose-400">V3.1 Sniper Target (Thử nghiệm lịch sử)</span>
                    <span className="text-[9px] px-1.5 py-0.5 bg-rose-900/30 rounded text-rose-400">frozen_inference.py</span>
                  </div>
                  <p className="text-slate-400 mb-2">Các thay đổi được đánh giá trong nghiên cứu V3.1:</p>
                  <ul className="list-disc pl-4 space-y-1 text-slate-300">
                    <li><span className="text-rose-300">Leakage safeguards</span> Sửa lỗi threshold và nhân chéo dữ liệu đa khung giờ.</li>
                    <li><span className="text-rose-300">Macro Context</span> Thêm btc_volatility_24h và funding_accumulated_7d.</li>
                    <li><span className="text-rose-300">Pre-filter</span> Gác cổng tự động loại bỏ các coin có biên độ bơm &lt;10%/24h.</li>
                    <li><span className="text-rose-300">Giới hạn cảnh báo</span> Một tham số nghiên cứu dùng để khảo sát quan hệ giữa độ phủ và precision.</li>
                  </ul>
                </div>
            {/* Section 2: Models Đang Dùng */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center space-x-2 mb-4">
                <Settings className="w-4 h-4 text-cyan-400" />
                <h3 className="text-xs font-bold text-slate-200 uppercase">2. Vai Trò Mô Hình Trong Nghiên Cứu Lịch Sử</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[11px] whitespace-nowrap">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-500 uppercase">
                      <th className="pb-2 font-medium">Vai trò</th>
                      <th className="pb-2 font-medium">Mô hình</th>
                      <th className="pb-2 font-medium">Kết quả nghiên cứu</th>
                      <th className="pb-2 font-medium">Phạm vi</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    <tr className="text-slate-300">
                      <td className="py-2"><span className="text-amber-400 font-medium">Champion</span></td>
                      <td className="py-2">LightGBM V3.1 (35 features)</td>
                      <td className="py-2 font-mono text-cyan-300">36.60% (Sniper)</td>
                      <td className="py-2"><span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">Historical</span></td>
                    </tr>
                    <tr className="text-slate-300">
                      <td className="py-2"><span className="text-purple-400 font-medium">Meta-labeling</span></td>
                      <td className="py-2">HistGradientBoosting</td>
                      <td className="py-2 font-mono text-slate-400">Gác cổng lọc nhiễu</td>
                      <td className="py-2"><span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">Historical</span></td>
                    </tr>
                    <tr className="text-slate-300">
                      <td className="py-2"><span className="text-blue-400 font-medium">Regime Gate</span></td>
                      <td className="py-2">ADX + BB + EMA (BTC 5m)</td>
                      <td className="py-2 font-mono text-cyan-300">Kết quả theo báo cáo</td>
                      <td className="py-2"><span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">Historical</span></td>
                    </tr>
                    <tr className="text-slate-300">
                      <td className="py-2"><span className="text-emerald-400 font-medium">Challenger</span></td>
                      <td className="py-2">LightGBM + Isotonic</td>
                      <td className="py-2 font-mono text-emerald-300 font-bold">20.93% (Altcoins)</td>
                      <td className="py-2"><span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">Historical</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Section 3: Regime Gate */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center space-x-2 mb-4">
                <Shield className="w-4 h-4 text-emerald-400" />
                <h3 className="text-xs font-bold text-slate-200 uppercase">3. Bộ Lọc Chế Độ Thị Trường (Regime Gate)</h3>
              </div>
              <p className="text-[11px] text-slate-400 mb-3">Phân loại cấu trúc thị trường để chỉ phát cảnh báo trong môi trường thuận lợi:</p>
              <div className="grid grid-cols-2 gap-3 text-[11px]">
                <div className="bg-slate-950 p-2.5 rounded border border-emerald-900/50">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-emerald-400">SIDEWAY_DISTRIBUTION</span>
                    <Check className="w-3 h-3 text-emerald-400" />
                  </div>
                  <p className="text-slate-400 mb-1">Thị trường đi ngang/phân phối trong thí nghiệm lưu trữ.</p>
                  <div className="text-cyan-300 font-bold">Kết quả: xem báo cáo lịch sử</div>
                </div>
                
                <div className="bg-slate-950 p-2.5 rounded border border-amber-900/50">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-amber-400">TRENDING_BEAR</span>
                    <Check className="w-3 h-3 text-emerald-400" />
                  </div>
                  <p className="text-slate-400 mb-1">Xu hướng giảm trong thí nghiệm lưu trữ.</p>
                  <div className="text-cyan-300 font-bold">Kết quả: xem báo cáo lịch sử</div>
                </div>

                <div className="bg-slate-950 p-2.5 rounded border border-red-900/50 opacity-70">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-red-400">TRENDING_BULL</span>
                    <X className="w-3 h-3 text-red-400" />
                  </div>
                  <p className="text-slate-400">Xu hướng tăng mạnh. Ngăn chặn bắt đỉnh sớm.</p>
                </div>

                <div className="bg-slate-950 p-2.5 rounded border border-red-900/50 opacity-70">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-red-400">HIGH_VOLATILITY</span>
                    <X className="w-3 h-3 text-red-400" />
                  </div>
                  <p className="text-slate-400">Nhiễu động lớn, spread quét râu. Chặn tín hiệu.</p>
                </div>
              </div>
            </div>

            {/* Section 4: Feature Importance */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-2">
                  <BarChart3 className="w-4 h-4 text-cyan-400" />
                  <h3 className="text-xs font-bold text-slate-200 uppercase">4. Độ Quan Trọng Đặc Trưng (Information Gain)</h3>
                </div>
                <span className="text-[9px] bg-slate-800 px-1.5 py-0.5 rounded text-slate-400">LightGBM (210 Coins)</span>
              </div>
              <div className="space-y-3 text-[11px]">
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="text-slate-300 font-mono">volatility_24h</span>
                    <span className="text-cyan-300 font-mono font-bold">536K</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-amber-400" style={{ width: '100%' }}></div>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="text-slate-300 font-mono">funding_rate_raw</span>
                    <span className="text-cyan-300 font-mono font-bold">296K</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-cyan-400" style={{ width: '55.2%' }}></div>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="text-slate-300 font-mono">top_acct_ratio</span>
                    <span className="text-cyan-300 font-mono font-bold">235K</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-cyan-400" style={{ width: '43.8%' }}></div>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="text-slate-300 font-mono">global_ls_ratio</span>
                    <span className="text-cyan-300 font-mono font-bold">218K</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-cyan-400" style={{ width: '40.6%' }}></div>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="text-slate-300 font-mono">return_24h</span>
                    <span className="text-cyan-300 font-mono font-bold">134K</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-cyan-400" style={{ width: '25%' }}></div>
                  </div>
                </div>
              </div>
            </div>
          </div>

            {/* Section 5: MLOps Insights */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 lg:col-span-2">
              <div className="flex items-center space-x-2 mb-4">
                <Shield className="w-4 h-4 text-rose-400" />
                <h3 className="text-xs font-bold text-slate-200 uppercase">5. Sổ tay kỹ thuật (ADR & MLOps Insights)</h3>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-[11px]">
                <div className="bg-slate-950 p-3 rounded border border-rose-900/30">
                  <div className="font-semibold text-rose-400 mb-2">Từ chối Mô hình 52% (Ảo ảnh Thống kê)</div>
                  <p className="text-slate-400 mb-1">Dù có Fold thử nghiệm đạt 52% Precision, mô hình vẫn bị loại bỏ do:</p>
                  <ul className="list-disc pl-4 space-y-1 text-slate-300">
                    <li><strong className="text-slate-200">Data Contamination:</strong> Calibrator (hiệu chuẩn) bị lệch pha vì huấn luyện trên 80% dữ liệu nhưng lại ghép với mô hình 100% dữ liệu.</li>
                    <li><strong className="text-slate-200">ECE &gt; 0.05:</strong> Sai số dự báo quá lớn khiến rủi ro Kelly Sizing tăng cao, dễ dẫn đến thanh lý lệnh.</li>
                  </ul>
                </div>
                <div className="bg-slate-950 p-3 rounded border border-emerald-900/30">
                  <div className="font-semibold text-emerald-400 mb-2">Quyết định tại thời điểm nghiên cứu V3.1</div>
                  <p className="text-slate-400 mb-1">Lý do V3.1 từng được chọn trong thí nghiệm lịch sử; đây không phải trạng thái production hiện tại:</p>
                  <ul className="list-disc pl-4 space-y-1 text-slate-300">
                    <li><strong className="text-slate-200">Robustness:</strong> Được huấn luyện trên Fold cuối cùng bao trùm 90% dữ liệu lịch sử sát với hiện tại nhất.</li>
                    <li><strong className="text-slate-200">Hiệu chuẩn:</strong> Được đánh giá trên tập của nghiên cứu; không suy rộng sang giai đoạn live mới hoặc dùng như bảo đảm định cỡ lệnh.</li>
                  </ul>
                </div>
              </div>
            </div>

          {/* Quick Access to Research Archive Banner */}
          <div className="bg-gradient-to-r from-amber-500/10 via-slate-900 to-cyan-500/10 border border-amber-500/30 rounded-lg p-4 flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="flex items-center space-x-3">
              <BookOpen className="w-6 h-6 text-amber-400 shrink-0" />
              <div>
                <h4 className="text-xs font-bold text-slate-100 uppercase">Khám Phá Thư Viện Nghiên Cứu Định Lượng</h4>
                <p className="text-[11px] text-slate-400">Xem các báo cáo lưu trữ với bảng dữ liệu, phân tích ROC-AUC và kết quả Walk-Forward theo từng cấu hình nghiên cứu.</p>
              </div>
            </div>
            <button
              onClick={() => setSubTab('RESEARCH')}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 rounded-lg border border-amber-500/50 text-xs font-semibold shrink-0 transition-colors"
            >
              <span>Xem Thư Viện Papers</span>
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ModelsDocTab;
