import React, { useState, useEffect, useCallback, useRef } from "react";
import TopBar from "./components/TopBar";
import KPIRow from "./components/KPIRow";
import StrategyPanel from "./components/StrategyPanel";
import TradeTable from "./components/TradeTable";
import MarketDataPage from "./pages/MarketDataPage";
import AnalyticsPage from "./pages/AnalyticsPage";
import UserCenterPage from "./pages/UserCenterPage";
import { api } from "./api";
import type { FrontendTrade, FrontendMarket } from "./api";
import type { StrategySlot } from "./types";

interface BackendStrategies {
  active_strategy: string;
  strategies: Record<string, {
    name: string;
    win_rate: number;
    params: {
      entry_second: number;
      gap_threshold: number;
      min_buy_price: number;
      bet_fraction: number;
      cooldown_seconds: number;
    };
  }>;
}

function backendToFrontendSlot(s: BackendStrategies["strategies"][string]): StrategySlot {
  return {
    name: s.name,
    entry: s.params.entry_second,
    gap: s.params.gap_threshold,
    prob: s.params.min_buy_price,
    cool: s.params.cooldown_seconds,
    dir: "both",
    fund: "fixed",
    fundParam: s.params.bet_fraction,
  };
}

export default function App() {
  const [activeTab, setActiveTab] = useState("trade");
  const [slots, setSlots] = useState<Record<number, StrategySlot>>({
    1: { name: "策略一", entry: 25, gap: 10, prob: 0.6, cool: 0, dir: "both", fund: "fixed", fundParam: 0.1 },
    2: { name: "策略二", entry: 120, gap: 100, prob: 0.9, cool: 3, dir: "both", fund: "fixed", fundParam: 0.1 },
    3: { name: "策略三", entry: 25, gap: 10, prob: 0.6, cool: 0, dir: "both", fund: "fixed", fundParam: 0.1 },
    4: { name: "策略四", entry: 25, gap: 10, prob: 0.6, cool: 0, dir: "both", fund: "fixed", fundParam: 0.1 },
    5: { name: "策略五", entry: 25, gap: 10, prob: 0.6, cool: 0, dir: "both", fund: "fixed", fundParam: 0.1 },
  });
  const [activeSlots, setActiveSlots] = useState<Record<number, boolean>>({ 1: true });
  const [simOn, setSimOn] = useState(false);
  const [liveOn, setLiveOn] = useState(false);

  // Real data from API
  const [countdown, setCountdown] = useState(0);
  const [btcPrice, setBtcPrice] = useState(0);
  const [openPrice, setOpenPrice] = useState(0);
  const [marketSlug, setMarketSlug] = useState("");
  const [marketTime, setMarketTime] = useState("");
  const [qualityStatus, setQualityStatus] = useState({ collector: false, orderbook: false, price: false, network: false });
  const [serviceStatus, setServiceStatus] = useState({ sim: false, live: false, route: false });

  // Data for child components
  const [trades, setTrades] = useState<FrontendTrade[]>([]);
  const [tradesTotal, setTradesTotal] = useState(0);
  const [markets, setMarkets] = useState<FrontendMarket[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [wallet, setWallet] = useState<any>(null);
  const [dataQuality, setDataQuality] = useState<any>(null);
  const [fundTrend, setFundTrend] = useState<any>({ data: [], initial: 100 });
  const [skipReasons, setSkipReasons] = useState<any>({ data: [], total: 0 });

  // ── Fast polling (5s): status + trades only ──
  const fetchingRef = useRef(false);
  const statRef = useRef<any>(null);
  const refreshFast = useCallback(async () => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    try {
      const [stat, tradesRes] = await Promise.all([
        api.status(),
        api.trades(1, 100),
      ]);

      // Update topbar data ONLY (no summary conflict)
      const t = stat.ticker;
      const m = stat.current_market;
      statRef.current = stat; // Save for refreshSlow bankroll fallback
      setBtcPrice(t.chainlink_price || t.btc_price || 0);
      setOpenPrice(t.ptb || t.open_price || 0);
      setCountdown(m.seconds_left || 0);
      setMarketSlug(m.slug || "");
      setMarketTime(`${new Date(m.window_start_ts * 1000).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}-${new Date(m.window_end_ts * 1000).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}`);
      setTickerUp(t.up_price || 0);
      setTickerDown(t.down_price || 0);

      // Update service status
      setSimOn(stat.sim?.service_active && !stat.stats?.sim ? false : stat.stats?.sim?.trade_count > 0);
      setServiceStatus({
        sim: stat.sim?.service_active || false,
        live: stat.live?.service_active || false,
        route: true,
      });

      // Update trades
      setTrades(tradesRes.trades);
      setTradesTotal(tradesRes.total);
    } catch (e) {
      console.error("refreshFast error:", e);
    } finally {
      fetchingRef.current = false;
    }
  }, []);

  // ── Quality polling (5s) ──
  const refreshQuality = useCallback(async () => {
    try {
      const q = await api.dataQuality();
      setDataQuality(q);
      setQualityStatus({
        collector: q.collector_running || false,
        orderbook: q.clob_ws_online || false,
        price: !q.rtds_degraded && q.rtds_chainlink_online,
        network: q.current_window_quality !== "bad",
      });
    } catch (e) {
      console.error("refreshQuality error:", e);
    }
  }, []);

  // ── Slow polling (30s): summary, strategies, wallet ──
  const refreshSlow = useCallback(async () => {
    try {
      const [safetyRes, summaryRes, stratRes, walletRes, trendRes, reasonsRes, statusRes] = await Promise.all([
        api.safety().catch(() => null),
        api.summary().catch(() => null),
        api.strategies().catch(() => null),
        api.wallet().catch(() => null),
        api.fundTrend().catch(() => ({ data: [], initial: 100 })),
        api.skipReasons().catch(() => ({ data: [], total: 0 })),
        api.status().catch(() => null),
      ]);

      if (safetyRes) {
        setSimOn(safetyRes.sim_trading || false);
        setLiveOn(safetyRes.ready_to_trade || false);
        setServiceStatus({
          sim: safetyRes.sim_active || false,
          live: safetyRes.live_connected || false,
          route: safetyRes.route_ready || false,
        });
      }

      // Get bankroll from status API (most reliable source)
      const statusBankroll = {
        sim: statusRes?.stats?.sim?.bankroll ?? statRef.current?.stats?.sim?.bankroll ?? 0,
        live: statusRes?.stats?.live?.bankroll ?? statRef.current?.stats?.live?.bankroll ?? 0,
      };

      if (summaryRes) {
        setSummary({
          total: summaryRes.total,
          confirmed: summaryRes.confirmed,
          won: summaryRes.won,
          lost: summaryRes.lost,
          skipped: summaryRes.skipped,
          win_rate: summaryRes.win_rate,
          total_pnl: summaryRes.total_pnl,
          total_amount: summaryRes.total_amount,
          daily_summary: summaryRes.daily_summary,
          sim_bankroll: statusBankroll.sim,
          live_bankroll: statusBankroll.live,
          sim_win_rate: statusRes?.stats?.sim?.win_rate ?? statRef.current?.stats?.sim?.win_rate ?? 0,
          live_win_rate: statusRes?.stats?.live?.win_rate ?? statRef.current?.stats?.live?.win_rate ?? 0,
        } as any);
      }

      if (stratRes) {
        const newSlots: Record<number, StrategySlot> = {};
        for (const [id, s] of Object.entries(stratRes.strategies)) {
          newSlots[Number(id)] = backendToFrontendSlot(s);
        }
        setSlots(newSlots);
      }

      if (walletRes) setWallet(walletRes);
      setFundTrend(trendRes);
      setSkipReasons(reasonsRes);
    } catch (e) {
      console.error("refreshSlow error:", e);
    }
  }, []);

  // ── Load markets on tab switch ──
  useEffect(() => {
    if (activeTab === "market" && markets.length === 0) {
      api.marketWindows(200).then(setMarkets).catch(console.error);
    }
  }, [activeTab, markets.length]);

  // ── Polling setup ──
  useEffect(() => {
    refreshFast();
    refreshQuality();
    refreshSlow();

    const fastId = setInterval(() => refreshFast(), 5000);
    const qualityId = setInterval(() => refreshQuality(), 5000);
    const slowId = setInterval(() => refreshSlow(), 30000);

    return () => {
      clearInterval(fastId);
      clearInterval(qualityId);
      clearInterval(slowId);
    };
  }, [refreshFast, refreshQuality, refreshSlow]);

  const gap = btcPrice - openPrice;
  const upProb = 0; // Will be set from API ticker
  const downProb = 0;
  const [tickerUp, setTickerUp] = useState(0);
  const [tickerDown, setTickerDown] = useState(0);

  // Update ticker prices from status
  // Mutual exclusion: starting one pauses the other
  const toggleSim = useCallback(async () => {
    const action = simOn ? "pause" : "start";
    try {
      await api.toggle(action, "sim");
      setSimOn(!simOn);
      if (!simOn) setLiveOn(false);
    } catch (e) {
      console.error("toggleSim error:", e);
    }
  }, [simOn]);

  const toggleLive = useCallback(async () => {
    const action = liveOn ? "pause" : "start";
    try {
      await api.toggle(action, "live");
      setLiveOn(!liveOn);
      if (!liveOn) setSimOn(false);
    } catch (e) {
      console.error("toggleLive error:", e);
    }
  }, [liveOn]);

  const toggleSlot = useCallback((n: number) => {
    setActiveSlots((prev) => {
      const next = { ...prev };
      if (next[n]) delete next[n]; else next[n] = true;
      return next;
    });
  }, []);

  const updateSlot = useCallback((n: number, data: Partial<StrategySlot>) => {
    setSlots((prev) => ({ ...prev, [n]: { ...prev[n], ...data } }));
  }, []);

  return (
    <div className="app-layout">
      <TopBar
        simOn={simOn} liveOn={liveOn} countdown={countdown}
        btcPrice={btcPrice} openPrice={openPrice} gap={gap}
        upProb={tickerUp} downProb={tickerDown}
        marketSlug={marketSlug} marketTime={marketTime}
        qualityStatus={qualityStatus} serviceStatus={serviceStatus}
        onToggleSim={toggleSim} onToggleLive={toggleLive}
        onRefresh={() => { refreshFast(); refreshQuality(); refreshSlow(); }}
      />
      <div className="app-content">
        <KPIRow summary={summary} fundTrend={fundTrend} />
        <div className="tab-nav" style={{ marginBottom: 0 }}>
          {[
            { key: "trade", label: "📊 交易控制" },
            { key: "market", label: "📈 市场数据" },
            { key: "analytics", label: "📉 数据分析" },
            { key: "user", label: "👤 用户中心" },
          ].map((t) => (
            <button key={t.key} className={`tab-nav-item ${activeTab === t.key ? "active" : ""}`}
              onClick={() => setActiveTab(t.key)}>{t.label}</button>
          ))}
        </div>
        <div className="app-main">
          <div className="left-panel">
            <StrategyPanel slots={slots} activeSlots={activeSlots}
              onToggleSlot={toggleSlot} onUpdateSlot={updateSlot} />
          </div>
          <div className="right-panel">
            {activeTab === "trade" && <TradeTable trades={trades} total={tradesTotal} mode={simOn ? "sim" : liveOn ? "live" : "none"} />}
            {activeTab === "market" && <MarketDataPage markets={markets} />}
            {activeTab === "analytics" && <AnalyticsPage summary={summary} fundTrend={fundTrend} skipReasons={skipReasons} />}
            {activeTab === "user" && <UserCenterPage wallet={wallet} dataQuality={dataQuality} />}
          </div>
        </div>
      </div>
    </div>
  );
}
