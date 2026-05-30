export type StrategyParams = {
  entry_second: number;
  gap_threshold: number;
  min_buy_price: number;
  bet_fraction: number;
  cooldown_seconds: number;
};

export type Strategy = {
  name: string;
  win_rate?: number;
  backtest_date?: string;
  params: StrategyParams;
};

export type StrategyConfig = {
  active_strategy: string;
  strategies: Record<string, Strategy>;
};

export type SafetyState = {
  executor: string;
  service_active: boolean;
  sim_active: boolean;
  browser_ready: boolean;
  clob_ready: boolean;
  live_connected?: boolean;
  route_ready?: boolean;
  armed: boolean;
  paused: boolean;
  sim_paused: boolean;
  ready_to_trade: boolean;
  sim_trading: boolean;
  checks: Array<{ name: string; ok: boolean; detail?: string }>;
};

export type BackendEvent = {
  time: string;
  type: "deposit" | "approval" | "order" | string;
  status: string;
  title: string;
  amount?: number;
  asset?: string;
  direction?: string;
  price?: number;
  shares?: number;
  from?: string;
  to?: string;
  order_id?: string;
  tx_hash?: string;
  tx_url?: string;
  relayer_tx_id?: string;
  note?: string;
};

export type WalletState = {
  route: string;
  network: string;
  chain_id: number;
  polygonscan: string;
  pUSD_token: string;
  pUSD_token_url: string;
  deposit_wallet: string;
  deposit_wallet_short: string;
  deposit_wallet_url: string;
  signer: string;
  signature_type: number;
  builder_key_present: boolean;
  clob_ok: boolean;
  clob_balance: number;
  allowance_ready: boolean;
  allowance_count: number;
  chain_pUSD_balance: number;
  native_pol: number;
  wallet_deployed: boolean;
  last_order?: BackendEvent | null;
  events: BackendEvent[];
};

export type BackendEventsResponse = {
  events: BackendEvent[];
};

export type DataQualityState = {
  collector_running?: boolean;
  current_market_slug?: string;
  slug?: string;
  market_window_id?: string;
  token_ids_ready?: boolean;
  clob_ws_online?: boolean;
  rtds_chainlink_online?: boolean;
  rtds_degraded?: boolean;
  last_orderbook_tick_age_ms?: number;
  last_price_tick_age_ms?: number;
  current_window_tick_count?: number;
  current_window_quality?: "good" | "degraded" | "bad" | "missing" | string;
  remaining_seconds?: number;
  status_age_ms?: number;
  price_last_value?: number;
  price_last_source?: string;
  orderbook_last_reason?: string;
  stats?: Record<string, number>;
  line_counts?: Record<string, number>;
  message?: string;
};

export type StatusState = {
  sim: { service_active: boolean };
  live: { service_active: boolean };
  collector: { service_active: boolean };
  ticker: Record<string, number | string | boolean>;
  current_market: Record<string, number | string | boolean>;
  executor_mode: string;
  trader_state: {
    bankroll: number;
    trade_count: number;
    win_count: number;
    loss_count: number;
    total_withdrawn: number;
  };
  stats?: {
    sim: TradingStats;
    live: TradingStats;
    total: TradingStats;
  };
};

export type TradingStats = {
  bankroll: number;
  trade_count: number;
  win_count: number;
  loss_count: number;
  total_withdrawn: number;
  win_rate: number;
};

export type SummaryState = {
  total: number;
  won: number;
  lost: number;
  skipped: number;
  failed: number;
  total_pnl: number;
  daily_summary: DailySummary[];
};

export type DailySummary = {
  date: string;
  trades: number;
  confirmed?: number;
  pending?: number;
  excluded?: number;
  pnl: number;
  wins: number;
  losses: number;
  skipped: number;
  volume: number;
};

export type TradeRow = {
  status: "won" | "lost" | "failed" | "skipped" | "pending" | "matched_lost";
  time: string;
  entry_time?: string | number;
  direction: "Up" | "Down" | "none" | string;
  mode?: "sim" | "live";
  slug: string;
  market_slug?: string;
  market_time?: string;
  window_start_ts?: number;
  window_end_ts?: number;
  btc_open: number | null;
  platform_open_price?: number | null;
  btc_entry: number;
  btc_final: number | null;
  platform_close_price?: number | null;
  entry_gap: number;
  buy_gap?: number | null;
  settle_gap: number | null;
  settlement_gap?: number | null;
  close_gap?: number | null;
  buy_prob: number;
  buy_amount: number;
  fee?: number | null;
  amount?: number;
  net_profit: number;
  pnl?: number;
  return_pct: number;
  settlement_status?: "pending" | "confirmed" | "fallback_missing" | "skipped" | string;
  settle_source?: string;
  settle_confirmed_at?: string | null;
  exclude_from_backtest?: boolean;
  skip_reason: string;
};

export type TradesResponse = {
  trades: TradeRow[];
  total: number;
  page: number;
  pages: number;
  per_page: number;
};

export type MarketWindowRow = {
  slug: string;
  window_start_ts: number;
  window_end_ts: number;
  market_time: string;
  open_price?: number | null;
  final_price?: number | null;
  final_gap?: number | null;
  winner?: string;
  ptb_quality?: string;
  token_ready?: boolean;
  has_trade?: boolean;
  trade_status?: string;
  reversal?: boolean;
};

export type MarketPricePoint = {
  ts: number;
  time: string;
  price: number;
  gap?: number | null;
  source?: string;
  lag_ms?: number | null;
};

export type MarketOrderbookPoint = {
  ts: number;
  time: string;
  reason?: string;
  up_prob?: number | null;
  down_prob?: number | null;
  up?: Record<string, number | string | null>;
  down?: Record<string, number | string | null>;
};

export type MarketDetail = {
  slug: string;
  window: MarketWindowRow & {
    open_price?: number | null;
    final_price?: number | null;
    final_gap?: number | null;
    winner?: string;
  };
  summary: {
    price_points: number;
    orderbook_points: number;
    trades: number;
    reversal: boolean;
    max_gap?: number | null;
    min_gap?: number | null;
    final_gap?: number | null;
  };
  prices: MarketPricePoint[];
  orderbook: MarketOrderbookPoint[];
  trades: TradeRow[];
};
