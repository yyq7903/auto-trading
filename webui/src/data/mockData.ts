// Mock data - covers all edge cases

export const mockTrades: any[] = [
  // === 05-29 recent trades (with all states) ===
  { time: "05-29 14:20-14:25", dir: "Up", open: 73820, btc: 73845, settle: null, gap: 25, settle_gap: "--", winner: "--", prob: 0.78, amount: 1.20, pnl: "--", ret: "--", status: "active", skip: "", entry: "T-25s", mode: "sim", fee: "--" },
  { time: "05-29 14:15-14:20", dir: "Down", open: 73810, btc: 73790, settle: null, gap: -20, settle_gap: "--", winner: "--", prob: 0.65, amount: 1.40, pnl: "--", ret: "--", status: "pending", skip: "待平台结算", entry: "T-20s", mode: "live", fee: "--" },
  { time: "05-29 14:10-14:15", dir: "Up", open: 73800, btc: 73830, settle: 73825, gap: 30, settle_gap: 25, winner: "Up", prob: 0.88, amount: 1.35, pnl: "+$0.09", ret: "+6.7%", status: "won", skip: "", entry: "T-23s", mode: "live", fee: "$0.007" },
  { time: "05-29 08:20-08:25", dir: "Up", open: 73680, btc: 73732, settle: 73722, gap: 52, settle_gap: 42, winner: "Up", prob: 0.92, amount: 1.59, pnl: "+$0.14", ret: "+8.8%", status: "won", skip: "", entry: "T-25s", mode: "sim", fee: "$0.008" },
  { time: "05-29 08:25-08:30", dir: "Down", open: 73739, btc: 73677, settle: null, gap: -62, settle_gap: "--", winner: "--", prob: 0, amount: 0, pnl: "--", ret: "--", status: "skipped", skip: "价格$0.000不可执行", entry: "T-1s", mode: "sim", fee: "--" },
  { time: "05-29 08:30-08:35", dir: "Down", open: 73675, btc: 73652, settle: 73656, gap: -23, settle_gap: -19, winner: "Down", prob: 0.98, amount: 1.73, pnl: "+$0.04", ret: "+2.3%", status: "won", skip: "", entry: "T-24s", mode: "sim", fee: "$0.009" },
  { time: "05-29 08:35-08:40", dir: "Up", open: 73656, btc: 73749, settle: 73739, gap: 93, settle_gap: 83, winner: "Up", prob: 0.97, amount: 1.76, pnl: "+$0.05", ret: "+2.8%", status: "won", skip: "", entry: "T-25s", mode: "sim", fee: "$0.009" },
  { time: "05-29 08:40-08:45", dir: "Down", open: 73739, btc: 73696, settle: 73748, gap: -43, settle_gap: 9, winner: "Up", prob: 0.64, amount: 1.82, pnl: "-$1.82", ret: "-100%", status: "lost", skip: "", entry: "T-18s", mode: "sim", fee: "$0.009" },
  { time: "05-29 08:45-08:50", dir: "Down", open: 73748, btc: 73653, settle: null, gap: -95, settle_gap: "--", winner: "--", prob: 0, amount: 0, pnl: "--", ret: "--", status: "skipped", skip: "价格$0.000不可执行", entry: "T-1s", mode: "sim", fee: "--" },
  { time: "05-29 08:50-08:55", dir: "Down", open: 73655, btc: 73640, settle: 73612, gap: -15, settle_gap: -43, winner: "Down", prob: 0.97, amount: 1.00, pnl: "+$0.03", ret: "+3.0%", status: "won", skip: "", entry: "T-25s", mode: "sim", fee: "$0.005" },
  { time: "05-29 08:55-09:00", dir: "Down", open: 73612, btc: 73604, settle: null, gap: -8, settle_gap: "--", winner: "--", prob: 0.01, amount: 0, pnl: "--", ret: "--", status: "skipped", skip: "gap<$10", entry: "T-1s", mode: "sim", fee: "--" },
  { time: "05-29 09:00-09:05", dir: "Up", open: 73620, btc: 73650, settle: 73640, gap: 30, settle_gap: 20, winner: "Up", prob: 0.85, amount: 1.20, pnl: "+$0.08", ret: "+6.7%", status: "won", skip: "", entry: "T-22s", mode: "sim", fee: "$0.006" },
  { time: "05-29 09:05-09:10", dir: "Down", open: 73650, btc: 73630, settle: 73635, gap: -20, settle_gap: -15, winner: "Down", prob: 0.72, amount: 1.50, pnl: "+$0.06", ret: "+4.0%", status: "won", skip: "", entry: "T-20s", mode: "sim", fee: "$0.008" },
  { time: "05-29 09:10-09:15", dir: "Up", open: 73635, btc: 73680, settle: 73670, gap: 45, settle_gap: 35, winner: "Up", prob: 0.88, amount: 1.30, pnl: "+$0.10", ret: "+7.7%", status: "won", skip: "", entry: "T-23s", mode: "sim", fee: "$0.007" },
  { time: "05-29 09:15-09:20", dir: "Down", open: 73680, btc: 73660, settle: null, gap: -20, settle_gap: "--", winner: "--", prob: 0.45, amount: 0, pnl: "--", ret: "--", status: "skipped", skip: "概率45%<60%", entry: "T-1s", mode: "sim", fee: "--" },
];

// Generate more trades for pagination testing
const dirs = ["Up", "Down"];
const skips = ["概率不足", "gap<$10", "价格不可执行", "PTB未获取", "无流动性"];
for (let i = 0; i < 150; i++) {
  const d = dirs[i % 2];
  const o = 73000 + Math.round(Math.random() * 300);
  const g = Math.round((Math.random() - 0.5) * 80);
  const isWon = Math.random() > 0.65;
  const isLost = !isWon && Math.random() > 0.8;
  const isActive = i < 2 && !isWon;
  const isPending = i >= 2 && i < 4 && !isWon;
  const day = i < 80 ? "05-29" : "05-28";
  const hour = 8 + Math.floor((i % 80) / 12);
  const min = (i % 12) * 5;
  const minEnd = min + 5;
  const status = isActive ? "active" : isPending ? "pending" : isWon ? "won" : isLost ? "lost" : "skipped";
  mockTrades.push({
    time: `${day} ${String(hour).padStart(2, "0")}:${String(min).padStart(2, "0")}-${String(hour + (minEnd >= 60 ? 1 : 0)).padStart(2, "0")}:${String(minEnd % 60).padStart(2, "0")}`,
    dir: d,
    prob: isWon ? (Math.random() * 0.3 + 0.65).toFixed(2) : (Math.random() * 0.5 + 0.1).toFixed(2),
    gap: g,
    open: o,
    btc: o + g,
    settle: isWon || isLost ? o + g - 10 : null,
    status,
    amount: isWon || isLost ? (Math.random() * 1.5 + 0.5).toFixed(2) : 0,
    pnl: isWon ? `+$${(Math.random() * 0.2 + 0.02).toFixed(2)}` : isLost ? `-$${(Math.random() * 2 + 0.5).toFixed(2)}` : "--",
    ret: isWon ? `+${(Math.random() * 10 + 2).toFixed(1)}%` : isLost ? `-${(Math.random() * 100 + 50).toFixed(0)}%` : "--",
    skip: isWon || isLost ? "" : skips[i % skips.length],
    entry: isWon || isLost ? `T-${Math.floor(Math.random() * 20) + 5}s` : "T-1s",
    winner: isWon ? d : isLost ? (d === "Up" ? "Down" : "Up") : "--",
    settle_gap: isWon || isLost ? g - 10 : "--",
    mode: i % 8 === 0 ? "live" : "sim",
    fee: isWon || isLost ? `$${(Math.random() * 0.01 + 0.003).toFixed(3)}` : "--",
  });
}

// Market list - 200+ records for pagination testing
export const mockMarkets = Array.from({ length: 250 }, (_, i) => {
  const day = i < 144 ? "05-29" : "05-28";
  const idx = i < 144 ? i : i - 144;
  const hour = 8 + Math.floor(idx / 12);
  const min = (idx % 12) * 5;
  const minEnd = min + 5;
  const winner = Math.random() > 0.5 ? "Up" : "Down";
  const gap = Math.round((Math.random() - 0.5) * 100);
  return {
    slug: `956700-${i}`,
    market_time: `${day} ${String(hour).padStart(2, "0")}:${String(min).padStart(2, "0")}-${String(hour + (minEnd >= 60 ? 1 : 0)).padStart(2, "0")}:${String(minEnd % 60).padStart(2, "0")}`,
    winner,
    final_gap: gap,
    has_trade: Math.random() > 0.85,
    trade_status: Math.random() > 0.5 ? "won" : "lost",
    reversal: Math.random() > 0.92,
  };
});

// Fund trend - dynamic days
export const mockFundTrend = {
  initial: 100,
  data: Array.from({ length: 60 }, (_, i) => {
    const day = 26 + Math.floor(i / 12);
    const hour = 8 + (i % 12);
    return {
      time: `2025-05-${day} ${String(hour).padStart(2, "0")}:00`,
      bankroll: 100 + i * 0.4 + Math.sin(i * 0.3) * 3,
      pnl: Math.random() * 1.5 - 0.3,
      slug: `956700-${i}`,
    };
  }),
};

export const mockSkipReasons = {
  total: 258,
  data: [
    { name: "概率不足", value: 89 },
    { name: "gap<$10", value: 67 },
    { name: "价格不可执行", value: 45 },
    { name: "PTB未获取", value: 32 },
    { name: "无流动性", value: 25 },
  ],
};

// Daily summary - multiple days, dynamic
export const mockDailySummary = [
  { date: "05-23", trades: 144, volume: 95.5, pnl: 5.2, wins: 4, losses: 2, skipped: 138, markets: 144, totalMarkets: 258, winRate: 66.7 },
  { date: "05-24", trades: 144, volume: 108.3, pnl: 7.8, wins: 5, losses: 1, skipped: 138, markets: 144, totalMarkets: 258, winRate: 83.3 },
  { date: "05-25", trades: 144, volume: 115.0, pnl: -2.1, wins: 3, losses: 4, skipped: 137, markets: 144, totalMarkets: 258, winRate: 42.9 },
  { date: "05-26", trades: 144, volume: 120.5, pnl: 8.3, wins: 6, losses: 1, skipped: 137, markets: 144, totalMarkets: 258, winRate: 85.7 },
  { date: "05-27", trades: 144, volume: 135.2, pnl: 10.1, wins: 7, losses: 2, skipped: 135, markets: 144, totalMarkets: 258, winRate: 77.8 },
  { date: "05-28", trades: 144, volume: 150.5, pnl: 12.3, wins: 8, losses: 2, skipped: 134, markets: 144, totalMarkets: 258, winRate: 80.0 },
  { date: "05-29", trades: 144, volume: 180.2, pnl: 15.7, wins: 10, losses: 3, skipped: 131, markets: 144, totalMarkets: 258, winRate: 76.9 },
];

// Win/loss streak history - each change event
export const mockStreakHistory = [
  { time: "05-23 08:05", type: "win", count: 1 },
  { time: "05-23 08:20", type: "win", count: 2 },
  { time: "05-23 08:35", type: "lose", count: 1 },
  { time: "05-23 09:00", type: "win", count: 1 },
  { time: "05-23 09:15", type: "win", count: 2 },
  { time: "05-23 09:30", type: "win", count: 3 },
  { time: "05-23 10:00", type: "lose", count: 1 },
  { time: "05-23 10:15", type: "lose", count: 2 },
  { time: "05-24 08:05", type: "win", count: 1 },
  { time: "05-24 08:20", type: "win", count: 2 },
  { time: "05-24 08:50", type: "win", count: 3 },
  { time: "05-24 09:05", type: "win", count: 4 },
  { time: "05-24 09:20", type: "win", count: 5 },
  { time: "05-24 09:35", type: "lose", count: 1 },
  { time: "05-25 08:10", type: "win", count: 1 },
  { time: "05-25 08:25", type: "lose", count: 1 },
  { time: "05-25 08:40", type: "lose", count: 2 },
  { time: "05-25 09:00", type: "lose", count: 3 },
  { time: "05-25 09:30", type: "win", count: 1 },
  { time: "05-25 09:45", type: "win", count: 2 },
  { time: "05-26 08:05", type: "win", count: 1 },
  { time: "05-26 08:20", type: "win", count: 2 },
  { time: "05-26 08:35", type: "win", count: 3 },
  { time: "05-26 08:50", type: "win", count: 4 },
  { time: "05-26 09:05", type: "win", count: 5 },
  { time: "05-26 09:20", type: "win", count: 6 },
  { time: "05-26 10:00", type: "lose", count: 1 },
  { time: "05-27 08:05", type: "win", count: 1 },
  { time: "05-27 08:35", type: "win", count: 2 },
  { time: "05-27 09:00", type: "win", count: 3 },
  { time: "05-27 09:15", type: "win", count: 4 },
  { time: "05-27 09:30", type: "win", count: 5 },
  { time: "05-27 09:45", type: "win", count: 6 },
  { time: "05-27 10:00", type: "win", count: 7 },
  { time: "05-27 10:15", type: "lose", count: 1 },
  { time: "05-27 10:30", type: "lose", count: 2 },
  { time: "05-28 08:05", type: "win", count: 1 },
  { time: "05-28 08:20", type: "win", count: 2 },
  { time: "05-28 08:50", type: "win", count: 3 },
  { time: "05-28 09:05", type: "win", count: 4 },
  { time: "05-28 09:20", type: "win", count: 5 },
  { time: "05-28 09:35", type: "win", count: 6 },
  { time: "05-28 09:50", type: "win", count: 7 },
  { time: "05-28 10:05", type: "win", count: 8 },
  { time: "05-28 10:20", type: "lose", count: 1 },
  { time: "05-28 10:35", type: "lose", count: 2 },
  { time: "05-29 08:05", type: "win", count: 1 },
  { time: "05-29 08:20", type: "win", count: 2 },
  { time: "05-29 08:35", type: "win", count: 3 },
  { time: "05-29 08:50", type: "win", count: 4 },
  { time: "05-29 09:05", type: "win", count: 5 },
  { time: "05-29 09:20", type: "win", count: 6 },
  { time: "05-29 09:35", type: "win", count: 7 },
  { time: "05-29 09:50", type: "win", count: 8 },
  { time: "05-29 10:05", type: "win", count: 9 },
  { time: "05-29 10:20", type: "win", count: 10 },
  { time: "05-29 10:35", type: "lose", count: 1 },
  { time: "05-29 10:50", type: "lose", count: 2 },
  { time: "05-29 11:05", type: "lose", count: 3 },
];

export const mockWalletEvents = [
  { time: "2025-05-29 14:15:00", type: "order", status: "pending", amount: 1.40, direction: "Down", price: 0.65, shares: 2.15, order_id: "0xpend001abc", tx_url: "" },
  { time: "2025-05-29 14:10:00", type: "order", status: "matched", amount: 1.35, direction: "Up", price: 0.88, shares: 1.53, order_id: "0xabc123def456", tx_url: "https://polygonscan.com/tx/0x123" },
  { time: "2025-05-29 08:20:00", type: "order", status: "matched", amount: 1.59, direction: "Up", price: 0.92, shares: 1.73, order_id: "0xdef789abc012", tx_url: "https://polygonscan.com/tx/0x456" },
  { time: "2025-05-29 07:00:00", type: "deposit", status: "confirmed", amount: 10.00, asset: "pUSD", order_id: "0xdep001", tx_url: "https://polygonscan.com/tx/0x789" },
  { time: "2025-05-28 22:00:00", type: "approval", status: "confirmed", amount: null, order_id: "0xapp001", tx_url: "https://polygonscan.com/tx/0xabc" },
];
