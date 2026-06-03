import React, { useState, useMemo, useCallback } from "react";
import type { FrontendTrade } from "../api";

const DEFAULT_TPP = 20;

interface Props {
  trades: FrontendTrade[];
  total: number;
  mode: "sim" | "live" | "none";
}

interface Filters {
  status: string[];
  mode: string[];
  dir: string[];
}

export default function TradeTable({ trades, total, mode }: Props) {
  const [page, setPage] = useState(1);
  const [tpp, setTpp] = useState(DEFAULT_TPP);
  const [showFilter, setShowFilter] = useState(false);
  const [filters, setFilters] = useState<Filters>({ status: [], mode: [], dir: [] });

  const toggleFilter = useCallback((key: keyof Filters, val: string) => {
    setFilters((prev) => {
      const arr = prev[key];
      const next = arr.includes(val) ? arr.filter((v) => v !== val) : [...arr, val];
      return { ...prev, [key]: next };
    });
    setPage(1);
  }, []);

  const clearFilters = useCallback(() => {
    setFilters({ status: [], mode: [], dir: [] });
    setPage(1);
  }, []);

  const filtered = useMemo(() => {
    return trades.filter((t) => {
      if (filters.status.length && !filters.status.includes(t.status)) return false;
      if (filters.mode.length && !filters.mode.includes(t.mode || "")) return false;
      if (filters.dir.length && !filters.dir.includes(t.dir)) return false;
      return true;
    });
  }, [trades, filters]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / tpp));
  const pageData = useMemo(() => {
    const start = (page - 1) * tpp;
    return filtered.slice(start, start + tpp);
  }, [filtered, page, tpp]);

  const exportCSV = () => {
    const header = "status,mode,time,dir,open,btc,settle,gap,settle_gap,result,prob,amount,fee,entry,pnl,ret,skip";
    const rows = filtered.map((t) =>
      [t.status, t.mode, t.time, t.dir, t.open, t.btc, t.settle ?? "--", t.gap, t.settle_gap, t.winner, t.prob, t.amount, t.fee, t.entry, t.pnl, t.ret, t.skip].join(",")
    ).join("\n");
    const blob = new Blob(["\ufeff" + header + "\n" + rows], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "trades.csv";
    a.click();
  };

  const pages = useMemo(() => {
    const ps: number[] = [];
    const s = Math.max(1, page - 2);
    const e = Math.min(totalPages, page + 2);
    for (let i = s; i <= e; i++) ps.push(i);
    return ps;
  }, [page, totalPages]);

  const rowClass = (status: string) => {
    if (status === "won") return "row-won";
    if (status === "lost") return "row-lost";
    if (status === "active") return "row-active";
    if (status === "pending") return "row-pending";
    return "row-skipped";
  };

  const statusBadge = (status: string) => {
    switch (status) {
      case "won": return <span className="badge won">盈利</span>;
      case "lost": return <span className="badge lost">亏损</span>;
      case "active": return <span className="badge active-badge">进行中</span>;
      case "pending": return <span className="badge pending-badge">待结算</span>;
      default: return <span className="badge skip">跳过</span>;
    }
  };

  const dv = (v: any) => {
    if (v === null || v === undefined || v === "" || v === "--") return <span style={{ color: "var(--muted)" }}>--</span>;
    return v;
  };

  const hasFilters = filters.status.length > 0 || filters.mode.length > 0 || filters.dir.length > 0;

  return (
    <div className="card" style={{ flex: 1, display: "flex", flexDirection: "column" }}>
      <div className="card-header">
        <div className="card-title">
          交易记录（最近{filtered.length}条 / 全量{total}）
          {hasFilters && <span style={{ color: "var(--accent)", fontSize: 10, marginLeft: 6 }}>已筛选</span>}
        </div>
        <div style={{ display: "flex", gap: 4, position: "relative" }}>
          <button className={`btn ${showFilter ? "active" : ""}`} style={{ fontSize: 10, padding: "4px 8px" }}
            onClick={() => setShowFilter(!showFilter)}>筛选</button>
          <button className="btn" style={{ fontSize: 10, padding: "4px 8px" }} onClick={exportCSV}>导出</button>
          {showFilter && (
            <div className="filter-dropdown show">
              <div style={{ fontSize: 10, fontWeight: 700, color: "var(--muted)", marginBottom: 6 }}>状态</div>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 8 }}>
                {[
                  { v: "won", l: "盈利" }, { v: "lost", l: "亏损" },
                  { v: "active", l: "进行中" }, { v: "pending", l: "待结算" }, { v: "skipped", l: "跳过" },
                ].map((s) => (
                  <button key={s.v} className={`btn ${filters.status.includes(s.v) ? "active" : ""}`}
                    style={{ fontSize: 10, padding: "2px 8px" }}
                    onClick={() => toggleFilter("status", s.v)}>{s.l}</button>
                ))}
              </div>
              <div style={{ fontSize: 10, fontWeight: 700, color: "var(--muted)", marginBottom: 6 }}>模式</div>
              <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
                {[{ v: "sim", l: "模拟" }, { v: "live", l: "实盘" }].map((m) => (
                  <button key={m.v} className={`btn ${filters.mode.includes(m.v) ? "active" : ""}`}
                    style={{ fontSize: 10, padding: "2px 8px" }}
                    onClick={() => toggleFilter("mode", m.v)}>{m.l}</button>
                ))}
              </div>
              <div style={{ fontSize: 10, fontWeight: 700, color: "var(--muted)", marginBottom: 6 }}>方向</div>
              <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
                {[{ v: "Up", l: "Up" }, { v: "Down", l: "Down" }].map((d) => (
                  <button key={d.v} className={`btn ${filters.dir.includes(d.v) ? "active" : ""}`}
                    style={{ fontSize: 10, padding: "2px 8px" }}
                    onClick={() => toggleFilter("dir", d.v)}>{d.l}</button>
                ))}
              </div>
              {hasFilters && (
                <button className="btn" style={{ fontSize: 10, padding: "2px 8px", width: "100%" }}
                  onClick={clearFilters}>清除筛选</button>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="card-body" style={{ padding: 0, flex: 1, overflow: "auto" }}>
        <table>
          <thead>
            <tr>
              <th style={{ width: 62 }}>状态</th>
              <th style={{ width: 52 }}>模式</th>
              <th style={{ width: 138 }}>时间</th>
              <th style={{ width: 62 }}>方向</th>
              <th style={{ width: 90 }}>开盘价</th>
              <th style={{ width: 90 }}>买入BTC</th>
              <th style={{ width: 90 }}>结算价</th>
              <th style={{ width: 68 }}>价差</th>
              <th style={{ width: 76 }}>结算价差</th>
              <th style={{ width: 88 }}>结算结果</th>
              <th style={{ width: 60 }}>概率</th>
              <th style={{ width: 72 }}>金额</th>
              <th style={{ width: 52 }}>手续费</th>
              <th style={{ width: 52 }}>入场</th>
              <th style={{ width: 76 }}>盈亏</th>
              <th style={{ width: 68 }}>盈亏率</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            {pageData.map((t, i) => (
              <tr key={i} className={rowClass(t.status)}>
                <td>{statusBadge(t.status)}</td>
                <td><span className={`badge ${t.mode === "live" ? "live-badge" : "skip"}`}>{t.mode === "live" ? "实盘" : "模拟"}</span></td>
                <td style={{ fontFamily: "JetBrains Mono", fontVariantNumeric: "tabular-nums", fontSize: 11, letterSpacing: "-0.02em" }}>{t.time}</td>
                <td><span className={`badge ${t.dir === "Up" ? "up" : "down"}`}>{t.dir}</span></td>
                <td style={{ fontFamily: "JetBrains Mono", fontVariantNumeric: "tabular-nums" }}>${typeof t.open === "number" ? t.open.toLocaleString() : t.open}</td>
                <td style={{ fontFamily: "JetBrains Mono", fontVariantNumeric: "tabular-nums" }}>${typeof t.btc === "number" ? t.btc.toLocaleString() : t.btc}</td>
                <td style={{ fontFamily: "JetBrains Mono", fontVariantNumeric: "tabular-nums" }}>{t.settle ? `$${Number(t.settle).toLocaleString()}` : dv("--")}</td>
                <td style={{ fontFamily: "JetBrains Mono", fontVariantNumeric: "tabular-nums" }} className={Number(t.gap) >= 0 ? "good" : "bad"}>{Number(t.gap) >= 0 ? "+" : ""}{t.gap}</td>
                <td style={{ fontFamily: "JetBrains Mono", fontVariantNumeric: "tabular-nums" }} className={Number(t.settle_gap) > 0 ? "good" : Number(t.settle_gap) < 0 ? "bad" : ""}>
                  {t.settle_gap === "--" ? dv("--") : `${Number(t.settle_gap) >= 0 ? "+" : ""}${t.settle_gap}`}
                </td>
                <td>
                  {t.winner === "--" || !t.winner ? dv("--") : (
                    <span className={`badge ${t.winner === t.dir ? "won" : "lost"}`}>{t.winner} {t.winner === t.dir ? "赢" : "输"}</span>
                  )}
                </td>
                <td style={{ fontFamily: "JetBrains Mono", fontVariantNumeric: "tabular-nums", fontSize: 11 }}>{typeof t.prob === "number" ? t.prob.toFixed(2) : t.prob}</td>
                <td style={{ fontFamily: "JetBrains Mono", fontVariantNumeric: "tabular-nums" }}>{t.amount === 0 || t.amount === "--" ? dv("--") : `$${Number(t.amount).toFixed(2)}`}</td>
                <td style={{ fontFamily: "JetBrains Mono", fontVariantNumeric: "tabular-nums", color: "var(--muted)" }}>{dv(t.fee)}</td>
                <td><span style={String(t.entry).includes("T-1s") ? { color: "var(--bad)" } : {}}>{t.entry}</span></td>
                <td style={{ fontFamily: "JetBrains Mono", fontVariantNumeric: "tabular-nums" }} className={String(t.pnl).startsWith("+") ? "good" : String(t.pnl).startsWith("-") ? "bad" : ""}>{dv(typeof t.pnl === "number" ? (t.pnl >= 0 ? "+" : "") + t.pnl.toFixed(2) : t.pnl)}</td>
                <td style={{ fontFamily: "JetBrains Mono", fontVariantNumeric: "tabular-nums" }} className={String(t.ret).startsWith("+") ? "good" : String(t.ret).startsWith("-") ? "bad" : ""}>{dv(t.ret)}</td>
                <td style={{ color: t.skip ? "var(--warn)" : "var(--muted)", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>{t.skip || dv("--")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pagination">
        <button className="page-btn" onClick={() => setPage(Math.max(1, page - 1))} disabled={page <= 1}>‹</button>
        {pages.map((p) => (
          <button key={p} className={`page-btn ${p === page ? "active" : ""}`} onClick={() => setPage(p)}>{p}</button>
        ))}
        <button className="page-btn" onClick={() => setPage(Math.min(totalPages, page + 1))} disabled={page >= totalPages}>›</button>
        <span style={{ fontSize: 10, color: "var(--muted)", margin: "0 8px" }}>{page}/{totalPages}</span>
        <select value={tpp} onChange={(e) => { setTpp(Number(e.target.value)); setPage(1); }}
          style={{ fontSize: 10, padding: "2px 4px", background: "var(--chip)", border: "1px solid var(--line)", color: "var(--text)", borderRadius: 4 }}>
          <option value={20}>20条/页</option>
          <option value={25}>25条/页</option>
          <option value={50}>50条/页</option>
          <option value={100}>100条/页</option>
        </select>
      </div>
    </div>
  );
}
