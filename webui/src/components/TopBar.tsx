import React from "react";

interface Props {
  simOn: boolean;
  liveOn: boolean;
  countdown: number;
  btcPrice: number;
  openPrice: number;
  gap: number;
  upProb: number;
  downProb: number;
  marketSlug?: string;
  marketTime?: string;
  qualityStatus?: { collector: boolean; orderbook: boolean; price: boolean; network: boolean };
  serviceStatus?: { sim: boolean; live: boolean; route: boolean };
  onToggleSim: () => void;
  onToggleLive: () => void;
  onRefresh: () => void;
}

export default function TopBar({
  simOn, liveOn, countdown, btcPrice, openPrice, gap, upProb, downProb,
  marketSlug, marketTime, qualityStatus, serviceStatus,
  onToggleSim, onToggleLive, onRefresh,
}: Props) {
  const mins = Math.floor(countdown / 60);
  const secs = countdown % 60;
  const signal = gap > 0 ? "BUY UP" : gap < 0 ? "BUY DOWN" : "---";
  const signalProb = gap > 0 ? upProb : downProb;
  const isUrgent = countdown <= 15;
  const isWarning = countdown <= 30 && countdown > 15;

  const qs = qualityStatus || { collector: false, orderbook: false, price: false, network: false };
  const ss = serviceStatus || { sim: false, live: false, route: false };
  const liveStartBlocked = !liveOn && !ss.route;

  return (
    <div className="topbar">
      <div className="topbar-left" style={{ gap: 6 }}>
        <div className="status-pill">
          <span className={`dot ${simOn || liveOn ? "green" : ""}`}
            style={!simOn && !liveOn ? { background: "var(--muted)" } : {}} />
          {simOn || liveOn ? "运行中" : "已暂停"}
        </div>
        <div className="status-pill" style={{ fontSize: 10 }}>
          市场 <b>{marketSlug || "--"}</b>{" "}<span style={{ color: "var(--muted)" }}>{marketTime || "--"}</span>
        </div>
        <div className="status-pill">现价 <b>${btcPrice > 0 ? btcPrice.toFixed(2) : "--"}</b></div>
        <div className="status-pill">开盘价 <b>${openPrice > 0 ? openPrice.toFixed(2) : "--"}</b></div>
        <div className="status-pill">价差 <b className={gap >= 0 ? "good" : "bad"}>{gap !== 0 ? (gap >= 0 ? "+" : "") + `$${gap.toFixed(2)}` : "--"}</b></div>
        <div className={`status-pill ${gap > 0 ? "up-pill" : ""}`}>Up <b>{upProb > 0 ? upProb.toFixed(3) : "0.000"}</b></div>
        <div className={`status-pill ${gap < 0 ? "down-pill" : ""}`}>Down <b>{downProb > 0 ? downProb.toFixed(3) : "0.000"}</b></div>
        <div className={`status-pill ${isUrgent ? "countdown-urgent" : isWarning ? "countdown-warning" : ""}`}
          style={isUrgent ? { borderColor: "rgba(239,68,68,.6)", animation: "pulse-countdown 1s infinite" } :
            isWarning ? { borderColor: "rgba(245,158,11,.4)" } : {}}>
          剩余 <b>{mins}:{secs < 10 ? "0" : ""}{secs}</b>
        </div>
        <div className="status-pill">
          <span style={{ color: gap > 0 ? "var(--good)" : gap < 0 ? "var(--bad)" : "var(--muted)", fontWeight: 700 }}>{signal}</span>{" "}
          <span style={{ fontSize: 9, color: "var(--muted)" }}>{signalProb > 0 ? (signalProb * 100).toFixed(0) + "%" : "--"}</span>
        </div>
        <div className="quality" style={{ marginLeft: 4 }}>
          <div className={`quality-tag ${qs.collector ? "ok" : "warn"}`}>采集器</div>
          <div className={`quality-tag ${qs.orderbook ? "ok" : "warn"}`}>盘口</div>
          <div className={`quality-tag ${qs.price ? "ok" : "warn"}`}>价格</div>
          <div className={`quality-tag ${qs.network ? "ok" : "warn"}`}>网络</div>
        </div>
        <div style={{ display: "flex", gap: 4, alignItems: "center", marginLeft: 8 }}>
          <button className={`btn ${simOn ? "active" : ""}`} style={{ fontSize: 10, padding: "3px 8px" }} onClick={onToggleSim}>模拟</button>
          <button className={`btn ${liveOn ? "active" : ""}`} style={{ fontSize: 10, padding: "3px 8px" }} onClick={onToggleLive}>实盘</button>
          <span style={{ fontSize: 10, color: "var(--muted)", marginLeft: 4 }}>
            <span className={`quality-tag ${ss.sim ? "ok" : "warn"}`} style={{ fontSize: 9, padding: "1px 4px" }}>服务{ss.sim ? "✓" : "✗"}</span>
          </span>
          <span style={{ fontSize: 10, color: "var(--muted)" }}>
            <span className={`quality-tag ${ss.live ? "ok" : "warn"}`} style={{ fontSize: 9, padding: "1px 4px" }}>实盘{ss.live ? "✓" : "✗"}</span>
          </span>
          <span style={{ fontSize: 10, color: "var(--muted)" }}>
            <span className={`quality-tag ${ss.route ? "ok" : "warn"}`} style={{ fontSize: 9, padding: "1px 4px" }}>路线{ss.route ? "✓" : "未就绪"}</span>
          </span>
        </div>
      </div>
      <div className="topbar-right">
        <button className={`btn ${simOn ? "success" : "primary"}`} onClick={onToggleSim}>{simOn ? "暂停模拟" : "启动模拟"}</button>
        <button
          className={`btn ${liveOn ? "danger" : ""}`}
          onClick={onToggleLive}
          disabled={liveStartBlocked}
          title={liveStartBlocked ? "实盘路线未就绪，已禁止从页面启动真实交易" : undefined}
        >
          {liveOn ? "暂停实盘" : "启动实盘"}
        </button>
        <button className="btn" onClick={onRefresh}>刷新</button>
      </div>
    </div>
  );
}
