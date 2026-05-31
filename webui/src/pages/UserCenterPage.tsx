import React from "react";

interface Props {
  wallet?: {
    route?: string;
    network?: string;
    chain_id?: number;
    deposit_wallet_short?: string;
    deposit_wallet_url?: string;
    signer?: string;
    clob_ok?: boolean;
    clob_balance?: number;
    allowance_ready?: boolean;
    chain_pUSD_balance?: number;
    native_pol?: number;
    wallet_deployed?: boolean;
    last_order?: { status: string } | null;
    events?: Array<{
      time: string;
      type: string;
      status: string;
      amount?: number;
      asset?: string;
      direction?: string;
      price?: number;
      shares?: number;
      order_id?: string;
      tx_url?: string;
      note?: string;
    }>;
  } | null;
  dataQuality?: {
    collector_running?: boolean;
    current_market_slug?: string;
    clob_ws_online?: boolean;
    rtds_chainlink_online?: boolean;
    rtds_degraded?: boolean;
    current_window_quality?: string;
    remaining_seconds?: number;
    current_window_tick_count?: number;
    price_last_value?: number;
    price_last_source?: string;
    status_age_ms?: number;
    stats?: Record<string, number>;
    line_counts?: Record<string, number>;
  } | null;
}

export default function UserCenterPage({ wallet, dataQuality }: Props) {
  const w = wallet || {};
  const dq = dataQuality || {};
  const events = w.events || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, height: "100%", overflow: "auto" }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
        {/* Connection status */}
        <div className="card">
          <div className="card-header"><div className="card-title">连接状态</div></div>
          <div className="card-body">
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                <span>采集器</span><span className={`badge ${dq.collector_running ? "won" : "lost"}`}>{dq.collector_running ? "运行中" : "未运行"}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                <span>盘口</span><span className={`badge ${dq.clob_ws_online ? "won" : "lost"}`}>{dq.clob_ws_online ? "在线" : "离线"}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                <span>官方价格</span><span className={`badge ${!dq.rtds_degraded && dq.rtds_chainlink_online ? "won" : "lost"}`}>{dq.rtds_degraded ? "降级" : dq.rtds_chainlink_online ? "在线" : "离线"}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                <span>交易接口</span><span className={`badge ${w.clob_ok ? "won" : "lost"}`}>{w.clob_ok ? "正常" : "异常"}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                <span>钱包部署</span><span className={`badge ${w.wallet_deployed ? "won" : "lost"}`}>{w.wallet_deployed ? "已部署" : "未确认"}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                <span>扣款授权</span><span className={`badge ${w.allowance_ready ? "won" : "pending-badge"}`}>{w.allowance_ready ? "已完成" : "待授权"}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Wallet info */}
        <div className="card">
          <div className="card-header"><div className="card-title">实盘资金</div></div>
          <div className="card-body">
            <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 11 }}>
              <div><span style={{ color: "var(--muted)" }}>下单方式:</span> {w.route || "--"}</div>
              <div><span style={{ color: "var(--muted)" }}>网络:</span> {w.network || "--"} / {w.chain_id || "--"}</div>
              <div><span style={{ color: "var(--muted)" }}>钱包:</span> {w.deposit_wallet_short || "--"}</div>
              <div><span style={{ color: "var(--muted)" }}>可下单余额:</span> <b>${(w.clob_balance ?? 0).toFixed(6)}</b></div>
              <div><span style={{ color: "var(--muted)" }}>链上余额:</span> ${(w.chain_pUSD_balance ?? 0).toFixed(6)}</div>
              <div><span style={{ color: "var(--muted)" }}>POL:</span> {(w.native_pol ?? 0).toFixed(4)}</div>
            </div>
          </div>
        </div>

        {/* Data quality */}
        <div className="card">
          <div className="card-header"><div className="card-title">数据质量</div></div>
          <div className="card-body">
            <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 11 }}>
              <div><span style={{ color: "var(--muted)" }}>质量:</span> <span className={`badge ${dq.current_window_quality === "good" ? "won" : dq.current_window_quality === "bad" ? "lost" : "skip"}`}>{dq.current_window_quality || "--"}</span></div>
              <div><span style={{ color: "var(--muted)" }}>当前市场:</span> {dq.current_market_slug || "--"}</div>
              <div><span style={{ color: "var(--muted)" }}>剩余秒数:</span> {dq.remaining_seconds ?? "--"}</div>
              <div><span style={{ color: "var(--muted)" }}>盘口数:</span> {dq.current_window_tick_count ?? 0}</div>
              <div><span style={{ color: "var(--muted)" }}>最新价格:</span> ${(dq.price_last_value ?? 0).toFixed(2)}</div>
              <div><span style={{ color: "var(--muted)" }}>价格来源:</span> {dq.price_last_source || "--"}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Events table */}
      <div className="card" style={{ flex: 1 }}>
        <div className="card-header"><div className="card-title">事件记录 ({events.length})</div></div>
        <div className="card-body" style={{ padding: 0, overflow: "auto" }}>
          <table>
            <thead>
              <tr><th>时间</th><th>类型</th><th>状态</th><th>金额</th><th>方向</th><th>订单号</th><th>说明</th></tr>
            </thead>
            <tbody>
              {events.map((e, i) => (
                <tr key={i}>
                  <td style={{ fontSize: 11 }}>{e.time}</td>
                  <td><span className={`badge ${e.type === "order" ? "up" : e.type === "deposit" ? "won" : "skip"}`}>{e.type === "order" ? "订单" : e.type === "deposit" ? "入金" : "授权"}</span></td>
                  <td><span className={`badge ${["confirmed", "matched", "success"].includes(e.status) ? "won" : "pending-badge"}`}>{e.status}</span></td>
                  <td style={{ fontFamily: "JetBrains Mono", fontSize: 11 }}>{e.amount ? `$${e.amount}` : "--"}</td>
                  <td>{e.direction ? <span className={`badge ${e.direction === "Up" ? "up" : "down"}`}>{e.direction}</span> : "--"}</td>
                  <td style={{ fontFamily: "JetBrains Mono", fontSize: 10, color: "var(--muted)" }}>{e.order_id ? `${e.order_id.slice(0, 10)}...` : "--"}</td>
                  <td style={{ color: "var(--muted)", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>{e.note || "--"}</td>
                </tr>
              ))}
              {!events.length && <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--muted)", padding: 20 }}>暂无事件</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
