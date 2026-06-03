import React, { useState } from "react";
import type { StrategySlot } from "../types";

interface Props {
  slots: Record<number, StrategySlot>;
  activeSlots: Record<number, boolean>;
  onToggleSlot: (n: number) => void;
  onUpdateSlot: (n: number, data: Partial<StrategySlot>) => void;
}

function cleanName(name: string): string {
  return name.replace(/[\(\（][^\)\）]*[\)\）]/g, "").trim();
}

export default function StrategyPanel({ slots, activeSlots, onToggleSlot, onUpdateSlot }: Props) {
  const [showModal, setShowModal] = useState(false);
  const [editSlot, setEditSlot] = useState(1);
  const [editForm, setEditForm] = useState<StrategySlot>(slots[1]);

  const activeKeys = Object.keys(activeSlots).map(Number);
  const firstActive = activeKeys.length > 0 ? slots[activeKeys[0]] : null;

  const openModal = () => {
    const n = activeKeys[0] || 1;
    setEditSlot(n);
    setEditForm({ ...slots[n] });
    setShowModal(true);
  };

  const saveModal = () => {
    onUpdateSlot(editSlot, editForm);
    setShowModal(false);
  };

  const dirText = (d: string) => d === "both" ? "双向" : d === "up" ? "只Up" : "只Down";
  const fundText = (s: StrategySlot) => s.fund === "fixed" ? `固定比例 ${Math.round(s.fundParam * 100)}%` : `固定金额 $${s.fundParam}`;

  return (
    <>
      <div className="card" style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div className="card-header">
          <div className="card-title">策略槽位</div>
          <button className="btn" onClick={openModal}>编辑</button>
        </div>
        <div className="card-body">
          <div className="strategy-slot-list">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                className={`btn strategy-btn ${activeSlots[n] ? "active" : ""}`}
                onClick={() => onToggleSlot(n)}
              >
                <span>策略 {n}</span>
                <b>{cleanName(slots[n].name)}</b>
                {slots[n].description ? (
                  <small title={slots[n].description}>
                    {slots[n].description.length > 30 ? `${slots[n].description.slice(0, 30)}...` : slots[n].description}
                  </small>
                ) : null}
              </button>
            ))}
          </div>
          <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 8 }}>
            当前后端执行策略：<span style={{ color: "var(--text)", fontWeight: 700 }}>{firstActive ? cleanName(firstActive.name) : "未选择"}</span>
          </div>
          {firstActive?.description ? (
            <div style={{
              fontSize: 11,
              color: "var(--text)",
              padding: "7px 9px",
              background: "rgba(59,130,246,.08)",
              border: "1px solid rgba(59,130,246,.24)",
              borderRadius: 6,
              marginBottom: 10,
              lineHeight: 1.5,
            }}>
              {firstActive.description}
            </div>
          ) : null}
          <div className="params-grid">
            <div className="param">
              <div className="k">入场窗口</div>
              <div className="v">{firstActive ? `T-${firstActive.entry}s` : "--"}</div>
            </div>
            <div className="param">
              <div className="k">价差阈值</div>
              <div className="v">{firstActive ? `>= $${firstActive.gap}` : "--"}</div>
            </div>
            <div className="param">
              <div className="k">最低概率</div>
              <div className="v">{firstActive ? `>= ${Math.round(firstActive.prob * 100)}%` : "--"}</div>
            </div>
            <div className="param">
              <div className="k">冷却市场</div>
              <div className="v">{firstActive ? firstActive.cool : "--"}</div>
            </div>
            <div className="param">
              <div className="k">方向过滤</div>
              <div className="v">{firstActive ? dirText(firstActive.dir) : "--"}</div>
            </div>
            <div className="param">
              <div className="k">资金模式</div>
              <div className="v">{firstActive ? fundText(firstActive) : "--"}</div>
            </div>
          </div>
          <div style={{ borderTop: "1px solid var(--line)", marginTop: 10, paddingTop: 10 }}>
            <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 6, fontWeight: 700 }}>当前策略参数</div>
            <div style={{
              fontSize: 11, color: "var(--text)", padding: "6px 8px",
              background: "var(--chip)", border: "1px solid var(--line)", borderRadius: 6,
            }}>
              {activeKeys.length === 0 ? (
                <div style={{ color: "var(--muted)" }}>未选择任何策略</div>
              ) : (
                activeKeys.slice(0, 1).map((n) => {
                  const s = slots[n];
                  return (
                    <div key={n} style={{ marginBottom: 2 }}>
                      {cleanName(s.name)}: T-{s.entry}s · gap{">="}${s.gap} · prob{">="}{Math.round(s.prob * 100)}% · 冷却{s.cool} · {dirText(s.dir)} · {fundText(s)}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Modal */}
      {showModal && (
        <div className="modal-overlay show" onClick={(e) => e.target === e.currentTarget && setShowModal(false)}>
          <div className="modal">
            <h3>编辑策略参数</h3>
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>保存到策略槽位</div>
              <div style={{ display: "flex", gap: 4 }}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    className={`btn ${editSlot === n ? "active" : ""}`}
                    onClick={() => { setEditSlot(n); setEditForm({ ...slots[n] }); }}
                  >
                    {cleanName(slots[n].name)}
                  </button>
                ))}
              </div>
            </div>
            <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12, marginBottom: 8, fontSize: 11, fontWeight: 700, color: "var(--accent)" }}>
              基础参数
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div>
                <label>入场窗口 (秒)</label>
                <input type="number" value={editForm.entry} min={1} max={300}
                  onChange={(e) => setEditForm({ ...editForm, entry: +e.target.value })} />
              </div>
              <div>
                <label>价差阈值 ($)</label>
                <input type="number" value={editForm.gap} min={0} max={500}
                  onChange={(e) => setEditForm({ ...editForm, gap: +e.target.value })} />
              </div>
              <div>
                <label>最低概率 (0.01-0.99)</label>
                <input type="number" value={editForm.prob} min={0.01} max={0.99} step={0.01}
                  onChange={(e) => setEditForm({ ...editForm, prob: +e.target.value })} />
              </div>
              <div>
                <label>冷却市场数 (0-100)</label>
                <input type="number" value={editForm.cool} min={0} max={100}
                  onChange={(e) => setEditForm({ ...editForm, cool: +e.target.value })} />
              </div>
              <div>
                <label>方向过滤</label>
                <select value={editForm.dir}
                  onChange={(e) => setEditForm({ ...editForm, dir: e.target.value as any })}>
                  <option value="both">双向</option>
                  <option value="up">只买Up</option>
                  <option value="down">只买Down</option>
                </select>
              </div>
              <div>
                <label>资金模式</label>
                <select value={editForm.fund}
                  onChange={(e) => setEditForm({ ...editForm, fund: e.target.value as any })}>
                  <option value="fixed">固定比例</option>
                  <option value="amount">固定金额</option>
                </select>
              </div>
              <div>
                <label>{editForm.fund === "fixed" ? "固定比例 (0.01-1.0)" : "固定金额 ($)"}</label>
                <input type="number" value={editForm.fundParam}
                  min={editForm.fund === "fixed" ? 0.01 : 1}
                  max={editForm.fund === "fixed" ? 1.0 : 100}
                  step={editForm.fund === "fixed" ? 0.01 : 1}
                  onChange={(e) => setEditForm({ ...editForm, fundParam: +e.target.value })} />
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 16, justifyContent: "flex-end" }}>
              <button className="btn" onClick={() => setShowModal(false)}>取消</button>
              <button className="btn primary" onClick={saveModal}>保存到策略槽位</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
