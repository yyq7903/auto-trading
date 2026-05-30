# RTDS 价格断流与盘口刷新指示 3

## 验收结论

`汇报3.md` 只通过了“窗口能切换”的一部分验收，但没有通过“现价 / 价差实时更新”的验收。

当前最严重问题：`price_ticks.jsonl` 只写了 59 条，最后一条停在 `2026-05-26T13:47:58Z` 左右。之后 WebUI 的 BTC 现价一直使用旧价格，所以现价和开盘价经常相同，价差也不动。

## 已确认现象

1. `data_quality.jsonl` 仍报告 `rtds_chainlink_online=true`，但 `last_price_tick_age_ms` 已经接近或超过 900,000ms。
2. `price_ticks.jsonl` 没有持续增长。
3. `stats.price_ticks=59` 长时间不变。
4. CLOB 盘口数据仍在增长，`price_change_ticks` 和 `orderbook_ticks` 都有新数据。
5. Up / Down 原本 5 秒刷新一次，是因为 WebUI API 读的是 periodic 合并盘口；Codex 已把 WebUI API 改为优先读取 `price_change_ticks` 的 `best_bid/best_ask`，可以比 5 秒更快，但采集器最好也输出实时合并盘口。

## Codex 已做的 WebUI API 临时修复

请不要覆盖以下改动：

1. 当官方 RTDS 价格超过 10 秒没有新 tick，WebUI 观察盘会使用外部 BTC 价格作为显示兜底。
2. 兜底来源会标记为 `binance_display_fallback` / `coinbase_display_fallback` / `kraken_display_fallback`，不能当作回测、结算或策略真实数据。
3. `/api/data-quality` 会在官方价格超过 15 秒无更新时把质量降为 `degraded`，并设置 `rtds_degraded=true`。
4. Up / Down 概率优先读取 `true_market/price_change_ticks.jsonl` 里的最新 `best_bid/best_ask`。

## Hermes 必须修复的根因

### 1. RTDS 不能只接收启动时的 59 条历史数组

你现在的 RTDS 连接看起来只收到一批历史 / buffer 数据，然后没有持续 update，但状态仍然显示在线。

要求：

- `price_ticks.jsonl` 必须持续增长。
- `last_price_tick_at` 必须接近当前时间。
- `last_price_tick_age_ms > 10000` 时，必须判定 RTDS 价格断流。
- 断流后必须自动重连并重新订阅。
- 重连后如果还是没有新 tick，`rtds_chainlink_online` 不能继续显示 `true`，必须显示 `false` 或 `rtds_degraded=true`。

### 2. 区分 WebSocket 在线和价格数据在线

WebSocket 连接在线不等于价格数据在线。请拆成两个字段：

- `rtds_ws_connected`
- `rtds_price_fresh`

验收条件：

- `rtds_price_fresh = last_price_tick_age_ms <= 10000`
- `rtds_chainlink_online` 只有在连接在线且价格新鲜时才为 `true`

### 3. PTB 不能用旧价格硬填

如果窗口开始时没有对应 Chainlink tick，不要把上一窗口的最后价格当成新窗口开盘价并标成可用。

正确做法：

- 没有真实窗口起点附近 tick：`ptb_pending=true` 或 `ptb_quality=bad`
- `exclude_from_backtest=true`
- WebUI 可以显示估算值，但必须标明不是官方开盘价

### 4. 盘口刷新

Codex 已在 WebUI API 层读取 `price_change_ticks`，但采集器也应该维护一个 `latest_book_snapshot.json` 或每次 `price_change` 后写一条合并快照，包含：

- `slug`
- `up_bid`
- `up_ask`
- `down_bid`
- `down_ask`
- `up_mid`
- `down_mid`
- `received_at`
- `source=price_change`

这样 WebUI 不需要每秒 tail 大文件，也不会只能等 5 秒 periodic。

## 下一份汇报要求

请新建 `汇报4.md`，不要编辑旧汇报。必须包含：

1. 连续 3 分钟内 `price_ticks.jsonl` 行数每 10 秒的变化。
2. `last_price_tick_age_ms` 连续样本，必须小于等于 10000ms。
3. `/api/data-quality` 摘要，证明 `rtds_chainlink_online` 不再在价格断流时假在线。
4. `/api/status` 连续 5 次样本，证明：
   - `btc_price` 会变化
   - `gap` 会变化
   - `source` 明确显示官方 RTDS 或显示兜底
   - `up_bid/up_ask/down_bid/down_ask` 可快于 5 秒更新
5. 如果 RTDS 官方端确实无法持续推送，必须写明备用方案，不准把外部交易所价格混入回测真实数据。

## 最终验收标准

1. 现价和价差不能长时间等于开盘价。
2. 官方价格源断流时，WebUI 必须显示“价格源降级”，不能显示“官方价格在线”。
3. Up / Down 能跟随 CLOB `price_change` 更新，不再只能等 5 秒 periodic。
4. 回测数据只能使用明确标记为 Polymarket / Chainlink 官方来源的价格；外部交易所价格只能用于 WebUI 观察。
