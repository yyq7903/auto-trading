# 市场切换与 WebUI 刷新指示 2

## 结论

`汇报2.md` 本次验收不通过。前端已经是 1 秒轮询，顶部状态栏“现价 / 开盘价 / 价差 / Up / Down”看起来不动的核心原因不是浏览器刷新慢，也不是 VPS 延迟，而是后端采集器仍然停在已结束的 5 分钟市场，继续向 WebUI 返回旧窗口数据。

## 已发现的失败证据

1. `/api/data-quality` 返回的窗口仍然是旧市场，`remaining_seconds` 已经为负数并继续变小，例如 `-615`。
2. `current_window_quality` 已被 WebUI API 判定为 `stale`。
3. `/api/status` 仍返回旧市场 `btc-updown-5m-1779801300`，`seconds_left=0`，盘口概率停留在 `Up 0.01 / Down 0.99`。
4. WebUI 顶部显示“剩余 0s”后没有切换到下一个市场。

## 必须修复的根因

采集器不能把“找不到精确 PTB / RTDS 缓冲不足 / Gamma 返回慢”当成继续写旧窗口的理由。窗口推进必须以墙钟时间为准。

正确逻辑：

1. 每 5 分钟根据当前时间计算 `expected_window_start_ts = floor(now / 300) * 300`。
2. 只要 `expected_window_start_ts` 大于当前窗口 start，就必须进入新窗口。
3. 如果新窗口的 Gamma 元数据、token id、PTB 暂时没拿到，仍然要创建“临时窗口状态”，标记：
   - `ptb_pending=true`
   - `current_window_quality=degraded` 或 `bad`
   - `reason=waiting_for_gamma_or_ptb`
4. 禁止继续把盘口、价格、质量状态写入已经结束超过 5 秒的旧窗口。
5. 当 `remaining_seconds < 0` 时，绝不能报告 `good`，必须是 `stale` 或 `bad`。

## RTDS / 价格刷新要求

1. 确认 RTDS Chainlink WebSocket 是否持续收到新 tick，而不是只收到启动时快照。
2. 如果 RTDS 断流或只给历史数组，必须自动重连并重新订阅。
3. `price_ticks.jsonl` 必须持续写入新 `timestamp/value/source`。
4. WebUI 的 `现价` 允许 1-3 秒延迟，但不能长时间不变。

## 必须新增的健康字段

请在 `data_quality.jsonl` 和 `/api/data-quality` 中增加以下字段，方便 WebUI 判断是否正在切换：

- `expected_window_start_ts`
- `current_window_start_ts`
- `last_successful_market_switch_at`
- `switch_lag_seconds`
- `negative_seconds_seen`
- `last_price_tick_at`
- `last_orderbook_tick_at`
- `market_switch_reason`

## WebUI 对接约束

Codex 已在 WebUI 侧做以下改动，你不要覆盖：

1. 顶部状态栏保持 1 秒刷新。
2. 当数据质量为 `stale` 或剩余秒数为负时，顶部会显示“市场切换中”。
3. 策略切换时显示“策略切换中”。
4. 交易控制只保留一个动态按钮：`启动模拟/暂停模拟` 或 `启动实盘/暂停实盘`。
5. 模拟资金可以在 WebUI 中手动设置。
6. 胜率拆成：模拟胜率、实盘胜率、总胜率。

如果你要修改 WebUI，必须先确认不会回退以上功能。

## 下一份汇报必须提供

请新建 `汇报3.md`，不要编辑旧汇报。里面必须包含：

1. 至少连续 3 个 5 分钟窗口的切换记录，也就是观察 15 分钟以上。
2. 每次切换的：
   - 旧 slug
   - 新 slug
   - old_start_ts
   - new_start_ts
   - switch_lag_seconds
   - remaining_seconds 是否一直在 `0-300` 范围内
3. `/api/status` 的 JSON 摘要，证明 slug、市场时间、现价、开盘价、Up、Down 都在新窗口更新。
4. `/api/data-quality` 的 JSON 摘要，证明没有 `remaining_seconds < 0` 的旧窗口继续输出。
5. WebUI 截图，截图时间必须覆盖至少一次窗口切换之后。
6. 如果 RTDS 断流，请说明重连次数、最后一次价格 tick 时间、fallback 数据源。

## 验收标准

只有同时满足以下条件，才算通过：

1. 当前市场结束后 5 秒内自动切换到下一个 5 分钟市场。
2. 顶部剩余秒数不再长时间停在 `0s`。
3. `现价` 至少能秒级或数秒级更新。
4. `Up / Down` 来自当前市场盘口，不能沿用旧市场盘口。
5. `/api/data-quality.current_window_quality` 不能在负秒数窗口里显示 `good`。
6. WebUI 页面刷新后仍显示当前最新市场，而不是旧窗口。
