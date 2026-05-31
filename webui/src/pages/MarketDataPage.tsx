import React, { useState, useEffect, useRef, useMemo } from "react";
import * as echarts from "echarts";
import type { FrontendMarket } from "../api";

const PAGE_SIZE = 20;

interface Props {
  markets: FrontendMarket[];
}

export default function MarketDataPage({ markets }: Props) {
  const [selected, setSelected] = useState(0);
  const [page, setPage] = useState(1);
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  const totalPages = Math.ceil(markets.length / PAGE_SIZE);
  const pageData = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return markets.slice(start, start + PAGE_SIZE);
  }, [markets, page]);

  const market = markets[selected];

  useEffect(() => {
    if (!chartRef.current || !market) return;
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current, "dark");
    }
    const chart = chartInstance.current;

    // Generate procedural chart data for the selected market
    const now = Date.now();
    const priceData: [number, number][] = [];
    const upData: [number, number][] = [];
    const downData: [number, number][] = [];
    const gapData: [number, number][] = [];
    const openPrice = 73000 + Math.random() * 500;

    for (let i = 0; i < 60; i++) {
      const ts = now - (60 - i) * 5000;
      const price = openPrice + (Math.random() - 0.5) * 100;
      const gap = price - openPrice;
      const up = Math.max(0.01, Math.min(0.99, 0.5 - gap / 200));
      priceData.push([ts, price]);
      gapData.push([ts, gap]);
      upData.push([ts, up]);
      downData.push([ts, 1 - up]);
    }

    chart.setOption({
      backgroundColor: "transparent",
      animation: false,
      color: ["#ff9b54", "#2f8cff", "#2ac769", "#ff4d4f"],
      legend: { textStyle: { color: "#9aa7b7" }, top: 0 },
      grid: { left: 58, right: 58, top: 48, bottom: 64 },
      tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
      dataZoom: [
        { type: "inside", xAxisIndex: [0] },
        { type: "slider", xAxisIndex: [0], bottom: 18, height: 22 },
      ],
      xAxis: { type: "time", axisLabel: { color: "#8797aa" }, splitLine: { lineStyle: { color: "#1f2b38" } } },
      yAxis: [
        { type: "value", name: "BTC", scale: true, axisLabel: { color: "#8797aa" }, splitLine: { lineStyle: { color: "#1f2b38" } } },
        { type: "value", name: "概率", min: 0, max: 1, axisLabel: { color: "#8797aa" }, splitLine: { show: false } },
      ],
      series: [
        { name: "BTC价格", type: "line", yAxisIndex: 0, showSymbol: false, data: priceData },
        { name: "Up概率", type: "line", yAxisIndex: 1, showSymbol: false, data: upData },
        { name: "Down概率", type: "line", yAxisIndex: 1, showSymbol: false, data: downData },
      ],
    });

    return () => { chart.dispose(); chartInstance.current = null; };
  }, [selected, market]);

  const rowClass = (status: string) => {
    if (status === "won") return "row-won";
    if (status === "lost") return "row-lost";
    return "";
  };

  if (!markets.length) {
    return <div className="card" style={{ padding: 40, textAlign: "center", color: "var(--muted)" }}>加载中...</div>;
  }

  return (
    <div style={{ display: "flex", gap: 10, height: "100%" }}>
      <div className="card" style={{ width: 340, display: "flex", flexDirection: "column" }}>
        <div className="card-header">
          <div className="card-title">市场列表</div>
          <span style={{ fontSize: 10, color: "var(--muted)" }}>{markets.length}条</span>
        </div>
        <div className="card-body" style={{ padding: 0, flex: 1, overflow: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>时间</th>
                <th>结果</th>
                <th>价差</th>
                <th>标记</th>
              </tr>
            </thead>
            <tbody>
              {pageData.map((m, i) => {
                const idx = (page - 1) * PAGE_SIZE + i;
                return (
                  <tr key={m.slug} className={idx === selected ? "row-selected" : ""}
                    style={{ cursor: "pointer" }} onClick={() => setSelected(idx)}>
                    <td style={{ fontSize: 11 }}>{m.market_time}</td>
                    <td>{m.winner !== "--" ? <span className={`badge ${m.winner === "Up" ? "up" : "down"}`}>{m.winner}</span> : <span style={{ color: "var(--muted)" }}>--</span>}</td>
                    <td style={{ fontFamily: "JetBrains Mono", fontSize: 11 }} className={m.final_gap >= 0 ? "good" : "bad"}>{m.final_gap >= 0 ? "+" : ""}{m.final_gap.toFixed(2)}</td>
                    <td>
                      {m.reversal && <span className="badge" style={{ color: "var(--warn)", borderColor: "rgba(245,158,11,.3)", background: "rgba(245,158,11,.08)" }}>反转</span>}
                      {m.has_trade && <span className={`badge ${m.trade_status === "lost" ? "lost" : "won"}`}>交易</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="pagination">
          <button className="page-btn" onClick={() => setPage(Math.max(1, page - 1))} disabled={page <= 1}>‹</button>
          <span style={{ fontSize: 10, color: "var(--muted)", margin: "0 8px" }}>{page}/{totalPages}</span>
          <button className="page-btn" onClick={() => setPage(Math.min(totalPages, page + 1))} disabled={page >= totalPages}>›</button>
        </div>
      </div>
      <div className="card" style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div className="card-header">
          <div className="card-title">市场回放 — {market?.slug || "--"}</div>
        </div>
        <div className="card-body" style={{ flex: 1, display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", gap: 12, marginBottom: 8, flexWrap: "wrap" }}>
            <div className="param"><div className="k">开盘价</div><div className="v">$--</div></div>
            <div className="param"><div className="k">结算价</div><div className="v">$--</div></div>
            <div className="param"><div className="k">结算差</div><div className="v">--</div></div>
            <div className="param"><div className="k">数据点</div><div className="v">--</div></div>
          </div>
          <div ref={chartRef} style={{ flex: 1, minHeight: 300 }} />
        </div>
      </div>
    </div>
  );
}
