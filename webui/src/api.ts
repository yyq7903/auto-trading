// API service layer — maps backend fields to frontend types

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

// ── Backend response types (matching api_server.py) ──

interface BackendTrade {
  status: string;
  time: string;
  entry_time?: number;
  entry_seconds_before?: number;
  direction: string;
  settlement_direction?: string;
  mode?: string;
  slug: string;
  market_slug?: string;
  window_start_ts?: number;
  window_end_ts?: number;
  market_time?: string;
  btc_open: number;
  btc_entry: number;
  btc_final: number | null;
  entry_gap: number;
  buy_gap: number;
  settlement_gap: number | null;
  buy_prob: number;
  buy_amount: number;
  fee: number | null;
  net_profit: number;
  return_pct: number;
  settlement_status?: string;
  skip_reason: string;
}

interface BackendTradesResponse {
  trades: BackendTrade[];
  total: number;
  page: number;
  pages: number;
  per_page: number;
}

interface BackendStatus {
  sim: { service_active: boolean };
  live: { service_active: boolean };
  collector: { service_active: boolean };
  current_market: {
    slug: string;
    window_start_ts: number;
    window_end_ts: number;
    seconds_left: number;
    ptb_quality: string;
    ptb_diff: number;
    exclude_from_backtest: boolean;
  };
  ticker: {
    btc_price: number;
    chainlink_price: number;
    ptb: number;
    open_price: number;
    gap: number;
    up_price: number;
    down_price: number;
    up_bid: number;
    up_ask: number;
    down_bid: number;
    down_ask: number;
    source: string;
    ptb_quality: string;
  };
  executor_mode: string;
  stats: {
    sim: { bankroll: number; trade_count: number; win_count: number; loss_count: number; total_withdrawn: number; win_rate: number };
    live: { bankroll: number; trade_count: number; win_count: number; loss_count: number; total_withdrawn: number; win_rate: number };
    total: { bankroll: number; trade_count: number; win_count: number; loss_count: number; total_withdrawn: number; win_rate: number };
  };
  trader_state: { bankroll: number; trade_count: number; win_count: number; loss_count: number; total_withdrawn: number };
}

interface BackendSummary {
  total: number;
  confirmed: number;
  pending: number;
  excluded: number;
  won: number;
  lost: number;
  skipped: number;
  failed: number;
  win_rate: number;
  total_pnl: number;
  total_amount: number;
  daily_summary: Array<{
    date: string;
    trades: number;
    confirmed: number;
    pending: number;
    excluded: number;
    pnl: number;
    wins: number;
    losses: number;
    skipped: number;
    volume: number;
  }>;
}

interface BackendSafety {
  executor: string;
  service_active: boolean;
  sim_active: boolean;
  browser_ready: boolean;
  clob_ready: boolean;
  live_connected: boolean;
  route_ready: boolean;
  armed: boolean;
  paused: boolean;
  sim_paused: boolean;
  mode: string;
  ready_to_trade: boolean;
  sim_trading: boolean;
  max_live_amount: number;
  checks: Array<{ name: string; ok: boolean }>;
}

interface BackendStrategies {
  active_strategy: string;
  strategies: Record<string, {
    name: string;
    win_rate: number;
    backtest_date: string;
    params: {
      entry_second: number;
      gap_threshold: number;
      min_buy_price: number;
      bet_fraction: number;
      cooldown_seconds: number;
    };
  }>;
}

interface BackendWallet {
  route: string;
  network: string;
  chain_id: number;
  deposit_wallet: string;
  deposit_wallet_short: string;
  deposit_wallet_url: string;
  signer: string;
  clob_ok: boolean;
  clob_balance: number;
  allowance_ready: boolean;
  chain_pUSD_balance: number;
  native_pol: number;
  wallet_deployed: boolean;
  last_order: { status: string } | null;
  events: Array<{
    time: string;
    type: string;
    status: string;
    amount?: number;
    asset?: string;
    direction?: string;
    price?: number;
    shares?: number;
    order_id?: string;
    tx_hash?: string;
    tx_url?: string;
    note?: string;
  }>;
}

interface BackendDataQuality {
  collector_running: boolean;
  current_market_slug: string;
  clob_ws_online: boolean;
  rtds_chainlink_online: boolean;
  rtds_degraded: boolean;
  current_window_quality: string;
  remaining_seconds: number;
  current_window_tick_count: number;
  price_last_value: number;
  price_last_source: string;
  status_age_ms: number;
  stats: Record<string, number>;
  line_counts: Record<string, number>;
}

interface BackendMarketWindows {
  markets: Array<{
    slug: string;
    window_start_ts: number;
    window_end_ts: number;
    market_time: string;
    open_price: number;
    final_price: number;
    final_gap: number;
    winner: string;
    ptb_quality: string;
    has_trade: boolean;
    trade_status: string;
    reversal: boolean;
  }>;
}

interface BackendFundTrend {
  data: Array<{ time: string; bankroll: number; pnl: number; slug: string }>;
  initial: number;
}

interface BackendSkipReasons {
  data: Array<{ name: string; value: number }>;
  total: number;
}

// ── Frontend types (matching new WebUI types.ts) ──

export interface FrontendTrade {
  time: string;
  dir: string;
  open: number;
  btc: number;
  settle: number | null;
  gap: number;
  settle_gap: number | string;
  winner: string;
  prob: number | string;
  amount: number | string;
  pnl: number | string;
  ret: string;
  status: "won" | "lost" | "skipped" | "active" | "pending";
  skip: string;
  entry: string;
  mode?: string;
  fee?: number | null;
  slug?: string;
}

export interface FrontendMarket {
  slug: string;
  market_time: string;
  winner: string;
  final_gap: number;
  has_trade: boolean;
  trade_status: string;
  reversal: boolean;
}

// ── Mapping functions ──

function mapTrade(t: BackendTrade): FrontendTrade {
  const dir = String(t.direction || "none").toLowerCase();
  const st = String(t.status || "").toLowerCase();
  let status: FrontendTrade["status"] = "skipped";
  if (st === "won") status = "won";
  else if (st === "lost" || st === "failed") status = "lost";
  else if (st === "active" || t.settlement_status === "active") status = "active";
  else if (st === "pending" || t.settlement_status === "pending") status = "pending";
  else if (st === "skipped") status = "skipped";

  const entrySec = t.entry_seconds_before;
  const entry = entrySec != null ? `T-${entrySec}s` : "--";

  return {
    time: t.market_time || t.time || "",
    dir: dir === "up" ? "Up" : dir === "down" ? "Down" : "--",
    open: t.btc_open || 0,
    btc: t.btc_entry || 0,
    settle: t.btc_final,
    gap: t.buy_gap ?? t.entry_gap ?? 0,
    settle_gap: t.settlement_gap ?? "--",
    winner: t.settlement_direction || "--",
    prob: t.buy_prob || 0,
    amount: t.buy_amount || 0,
    pnl: t.net_profit || 0,
    ret: t.return_pct ? `${t.return_pct > 0 ? "+" : ""}${t.return_pct.toFixed(1)}%` : "--",
    status,
    skip: t.skip_reason || "",
    entry,
    mode: t.mode || "",
    fee: t.fee,
    slug: t.slug,
  };
}

function mapMarket(m: BackendMarketWindows["markets"][0]): FrontendMarket {
  return {
    slug: m.slug,
    market_time: m.market_time,
    winner: m.winner || "--",
    final_gap: m.final_gap ?? 0,
    has_trade: m.has_trade,
    trade_status: m.trade_status || "",
    reversal: m.reversal,
  };
}

// ── API methods ──

export const api = {
  status: () => request<BackendStatus>("/api/status"),
  safety: () => request<BackendSafety>("/api/safety"),
  summary: () => request<BackendSummary>("/api/summary"),
  strategies: () => request<BackendStrategies>("/api/strategies"),
  wallet: () => request<BackendWallet>("/api/wallet"),
  dataQuality: () => request<BackendDataQuality>("/api/data-quality"),

  trades: async (page = 1, pageSize = 25): Promise<{ trades: FrontendTrade[]; total: number; page: number; pages: number }> => {
    const res = await request<BackendTradesResponse>(`/api/trades?p=${page}&ps=${pageSize}`);
    return {
      trades: res.trades.map(mapTrade),
      total: res.total,
      page: res.page,
      pages: res.pages,
    };
  },

  marketWindows: async (limit = 200): Promise<FrontendMarket[]> => {
    const res = await request<BackendMarketWindows>(`/api/market-windows?limit=${limit}`);
    return res.markets.map(mapMarket);
  },

  fundTrend: () => request<BackendFundTrend>("/api/fund-trend"),
  skipReasons: () => request<BackendSkipReasons>("/api/skip-reasons"),

  toggle: (action: "start" | "pause", mode: "sim" | "live") =>
    request("/api/toggle", { method: "POST", body: JSON.stringify({ action, mode }) }),

  switchStrategy: (id: string) =>
    request("/api/strategies/switch", { method: "POST", body: JSON.stringify({ strategy_id: id }) }),

  updateStrategy: (id: string, name: string, params: Record<string, number>) =>
    request("/api/strategies/update", { method: "POST", body: JSON.stringify({ strategy_id: id, name, params }) }),

  setSimFunds: (amount: number) =>
    request("/api/sim/funds", { method: "POST", body: JSON.stringify({ amount }) }),

  refreshBackend: () =>
    request("/api/refresh", { method: "POST", body: JSON.stringify({}) }),
};
