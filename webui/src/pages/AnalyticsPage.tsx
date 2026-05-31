import React, { useEffect, useRef } from "react";
import * as echarts from "echarts";

interface Props {
  summary?: {
    total?: number;
    confirmed?: number;
    skipped?: number;
    win_rate?: number;
    total_pnl?: number;
    total_amount?: number;
    won?: number;
    lost?: number;
    daily_summary?: Array<{
      date: string;
      trades: number;
      pnl: number;
      wins: number;
      losses: number;
      skipped: number;
      volume: number;
      markets?: number;
    }>;
  } | null;
  fundTrend?: {
    data: Array<{ time: string; bankroll: number; pnl: number; slug: string }>;
    initial: number;
  };
  skipReasons?: {
    data: Array<{ name: string; value: number }>;
    total: number;
  };
}

export default function AnalyticsPage({ summary, fundTrend, skipReasons }: Props) {
  const chartRefs = useRef<Record<string, echarts.ECharts>>({});

  const s = summary || {};
  const days = s.daily_summary || [];
  const trend = fundTrend?.data || [];
  const reasons = skipReasons?.data || [];

  useEffect(() => {
    const initChart = (id: string, option: echarts.EChartsOption) => {
      const el = document.getElementById(id);
      if (!el) return;
      const chart = echarts.init(el, "dark");
      chart.setOption(option);
      chartRefs.current[id] = chart;
    };

    // 1. Fund trend
    initChart("fundTrendChart", {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: trend.map((d) => d.time.slice(5, 16)), axisLabel: { rotate: 30, fontSize: 10 } },
      yAxis: { type: "value", axisLabel: { fontSize: 10 } },
      series: [{ type: "line", smooth: true, name: "资金", data: trend.map((d) => d.bankroll), areaStyle: { color: "rgba(139,92,246,0.2)" }, lineStyle: { color: "#8b5cf6" }, itemStyle: { color: "#8b5cf6" } }],
      grid: { left: 60, right: 20, top: 30, bottom: 60 },
    });

    // 2. Daily PnL
    initChart("dailyPnlChart", {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: days.map((d) => d.date), axisLabel: { fontSize: 10 } },
      yAxis: { type: "value", axisLabel: { fontSize: 10 } },
      series: [{ type: "bar", name: "盈亏", data: days.map((d) => d.pnl), itemStyle: { color: (p: any) => p.value >= 0 ? "#22c55e" : "#ef4444", borderRadius: [4, 4, 0, 0] } }],
      grid: { left: 60, right: 20, top: 20, bottom: 40 },
    });

    // 3. Daily win rate
    initChart("winRateChart", {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis", formatter: (p: any) => `${p[0].name}<br/>胜率: ${p[0].value}%` },
      xAxis: { type: "category", data: days.map((d) => d.date), axisLabel: { fontSize: 10 } },
      yAxis: { type: "value", min: 0, max: 100, axisLabel: { fontSize: 10, formatter: "{value}%" } },
      series: [{
        type: "line", smooth: true, name: "胜率",
        data: days.map((d) => d.trades > 0 ? Number(((d.wins / (d.wins + d.losses || 1)) * 100).toFixed(1)) : 0),
        areaStyle: { color: "rgba(34,197,94,0.2)" }, lineStyle: { color: "#22c55e" }, itemStyle: { color: "#22c55e" },
      }],
      grid: { left: 60, right: 20, top: 20, bottom: 40 },
    });

    // 4. Daily traded markets
    initChart("tradedMarketsChart", {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: days.map((d) => d.date), axisLabel: { fontSize: 10 } },
      yAxis: { type: "value", axisLabel: { fontSize: 10 } },
      series: [
        { type: "bar", name: "成交", data: days.map((d) => d.wins + d.losses), itemStyle: { color: "#3b82f6", borderRadius: [4, 4, 0, 0] } },
        { type: "bar", name: "跳过", data: days.map((d) => d.skipped), itemStyle: { color: "#6b7a9e", borderRadius: [4, 4, 0, 0] } },
      ],
      grid: { left: 60, right: 20, top: 20, bottom: 40 },
    });

    // 5. Skip reasons pie
    initChart("skipReasonChart", {
      backgroundColor: "transparent",
      tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
      legend: { orient: "vertical", right: 10, top: "center", textStyle: { color: "#fff", fontSize: 10 } },
      series: [{
        type: "pie", radius: ["40%", "70%"],
        itemStyle: { borderRadius: 6, borderColor: "#121726", borderWidth: 2 },
        label: { show: false },
        data: reasons.map((d, i) => ({ ...d, itemStyle: { color: ["#ef4444", "#f59e0b", "#eab308", "#22c55e", "#3b82f6", "#8b5cf6"][i % 6] } })),
      }],
    });

    const handleResize = () => {
      Object.values(chartRefs.current).forEach((c) => c.resize());
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      Object.values(chartRefs.current).forEach((c) => c.dispose());
      chartRefs.current = {};
    };
  }, [trend, days, reasons]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, height: "100%", overflow: "auto" }}>
      {/* Summary stats */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <div className="param"><div className="k">总交易</div><div className="v">{s.total ?? 0}</div></div>
        <div className="param"><div className="k">已确认</div><div className="v">{s.confirmed ?? 0}</div></div>
        <div className="param"><div className="k">已跳过</div><div className="v">{s.skipped ?? 0}</div></div>
        <div className="param"><div className="k">胜率</div><div className="v">{(s.win_rate ?? 0).toFixed(1)}%</div></div>
        <div className="param"><div className="k">总PnL</div><div className={`v ${(s.total_pnl ?? 0) >= 0 ? "good" : "bad"}`}>{(s.total_pnl ?? 0) >= 0 ? "+" : ""}${(s.total_pnl ?? 0).toFixed(2)}</div></div>
        <div className="param"><div className="k">总投入</div><div className="v">${(s.total_amount ?? 0).toFixed(2)}</div></div>
        <div className="param"><div className="k">今日市场</div><div className="v">{summary?.daily_summary?.[0]?.markets ?? 0}</div></div>
      </div>

      {/* Charts grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, flex: 1 }}>
        <div className="card" style={{ display: "flex", flexDirection: "column" }}>
          <div className="card-header"><div className="card-title">资金变化趋势</div></div>
          <div className="card-body" style={{ flex: 1 }}><div id="fundTrendChart" style={{ width: "100%", height: 250 }} /></div>
        </div>
        <div className="card" style={{ display: "flex", flexDirection: "column" }}>
          <div className="card-header"><div className="card-title">每日盈亏</div></div>
          <div className="card-body" style={{ flex: 1 }}><div id="dailyPnlChart" style={{ width: "100%", height: 250 }} /></div>
        </div>
        <div className="card" style={{ display: "flex", flexDirection: "column" }}>
          <div className="card-header"><div className="card-title">每日胜率</div></div>
          <div className="card-body" style={{ flex: 1 }}><div id="winRateChart" style={{ width: "100%", height: 250 }} /></div>
        </div>
        <div className="card" style={{ display: "flex", flexDirection: "column" }}>
          <div className="card-header"><div className="card-title">每日成交市场数</div></div>
          <div className="card-body" style={{ flex: 1 }}><div id="tradedMarketsChart" style={{ width: "100%", height: 250 }} /></div>
        </div>
        <div className="card" style={{ display: "flex", flexDirection: "column" }}>
          <div className="card-header"><div className="card-title">跳过原因分布</div></div>
          <div className="card-body" style={{ flex: 1 }}><div id="skipReasonChart" style={{ width: "100%", height: 250 }} /></div>
        </div>

        {/* Daily detail table */}
        <div className="card" style={{ display: "flex", flexDirection: "column" }}>
          <div className="card-header"><div className="card-title">每日明细</div></div>
          <div className="card-body" style={{ padding: 0, flex: 1, overflow: "auto" }}>
            <table>
              <thead><tr><th>日期</th><th>交易量</th><th>投入</th><th>盈亏</th><th>赢</th><th>输</th><th>跳过</th></tr></thead>
              <tbody>
                {days.map((d) => (
                  <tr key={d.date}>
                    <td>{d.date}</td>
                    <td>{d.trades}</td>
                    <td>${d.volume.toFixed(2)}</td>
                    <td className={d.pnl >= 0 ? "good" : "bad"}>{d.pnl >= 0 ? "+" : ""}${d.pnl.toFixed(2)}</td>
                    <td className="good">{d.wins}</td>
                    <td className="bad">{d.losses}</td>
                    <td>{d.skipped}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
