import type { AnalyticsState, BackendEventsResponse, DataQualityState, MarketDetail, MarketWindowRow, SafetyState, StatusState, StrategyConfig, SummaryState, TradesResponse, WalletState } from "./types";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    try {
      const body = JSON.parse(text);
      throw new Error(body.error || text || `${res.status} ${res.statusText}`);
    } catch (error) {
      if (error instanceof Error && error.message !== text) throw error;
      throw new Error(text || `${res.status} ${res.statusText}`);
    }
  }
  return res.json();
}

export const api = {
  safety: () => request<SafetyState>("/api/safety"),
  status: () => request<StatusState>("/api/status"),
  summary: () => request<SummaryState>("/api/summary"),
  wallet: () => request<WalletState>("/api/wallet"),
  dataQuality: () => request<DataQualityState>("/api/data-quality"),
  backendEvents: () => request<BackendEventsResponse>("/api/backend-events"),
  strategies: async () => {
    const res = await request<Record<string, any> | StrategyConfig>("/api/strategies");
    if ("strategies" in res) return res as StrategyConfig;
    return { active_strategy: "1", strategies: res as StrategyConfig["strategies"] };
  },
  trades: (page: number, pageSize = 20) => request<TradesResponse>(`/api/trades?p=${page}&ps=${pageSize}`),
  switchStrategy: (strategy_id: string) =>
    request("/api/strategies/switch", {
      method: "POST",
      body: JSON.stringify({ strategy_id }),
    }),
  updateStrategy: (strategy_id: string, name: string, params: Record<string, number>) =>
    request("/api/strategies/update", {
      method: "POST",
      body: JSON.stringify({ strategy_id, name, params }),
    }),
  toggle: (action: "start" | "pause", mode: "sim" | "live") =>
    request("/api/toggle", {
      method: "POST",
      body: JSON.stringify({ action, mode }),
    }),
  setSimFunds: (amount: number) =>
    request("/api/sim/funds", {
      method: "POST",
      body: JSON.stringify({ amount }),
    }),
  refreshBackend: () =>
    request("/api/refresh", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  fundTrend: () => request<{data: Array<{time: string, bankroll: number, pnl: number, slug: string}>, initial: number}>("/api/fund-trend"),
  skipReasons: () => request<{data: Array<{name: string, value: number}>, total: number}>("/api/skip-reasons"),
  marketWindows: () => request<{markets: MarketWindowRow[]}>("/api/market-windows?limit=180"),
  marketDetail: (slug: string) => request<MarketDetail>(`/api/market-detail?slug=${encodeURIComponent(slug)}`),
  analytics: () => request<AnalyticsState>("/api/analytics"),
};
