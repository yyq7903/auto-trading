# 给 Hermes 的当前任务与约束

当前阶段目标：数据采集 + 模拟盘 + WebUI 数据质量展示一起推进。禁止继续做新的真实下注，禁止改实盘下单主路径。

## 必须遵守的约束

1. 不准自动实盘下单
   - 不要调用真实 `place_order`。
   - 不要把 WebUI 的“启动实盘”接成自动循环。
   - 只能读余额、读订单、读链上、读接口状态。

2. 不准覆盖密钥和钱包配置
   - 不改 `.env` 里的私钥、Builder key、FUNDER_ADDRESS。
   - 不重新创建 builder key，除非用户和 Codex 都明确要求。

3. 数据文件只追加，不删除
   - 所有采集数据写 jsonl。
   - 不重写旧 `trades.jsonl`、不清空旧数据。
   - 如果字段结构升级，新建 `schema_version` 字段。

4. 模拟盘可以运行，但必须和实盘隔离
   - 模拟盘只读采集器数据，不调用实盘下单模块。
   - 模拟盘每笔订单加 `mode: "sim"`。
   - 实盘测试订单加 `mode: "live"`，不能混在一起统计。

5. WebUI 接入先做只读展示
   - 可以新增“数据质量”卡片。
   - 可以展示 WebSocket 在线、最近 tick 延迟、当前市场 token 是否完整。
   - 不要新增会真实扣钱的按钮。

6. 所有不确定数据必须标注来源
   - `source=polymarket_clob_ws`：平台盘口。
   - `source=polymarket_gamma`：平台市场元数据。
   - `source=polymarket_rtds_chainlink`：平台 RTDS Chainlink。
   - `source=chainlink_latestRoundData_fallback`：普通 Chainlink 备用，不等同平台最终数据。
   - `source=binance_fallback`：只能参考，不能当真实回测结算依据。

## 问题 1：RTDS Chainlink WebSocket 正确订阅方式

官方文档说明 RTDS 端点是：

```text
wss://ws-live-data.polymarket.com
```

Chainlink 订阅消息必须这样发。注意 `filters` 是字符串，不是对象：

```json
{
  "action": "subscribe",
  "subscriptions": [
    {
      "topic": "crypto_prices_chainlink",
      "type": "*",
      "filters": "{\"symbol\":\"btc/usd\"}"
    }
  ]
}
```

也可以先订阅全部 Chainlink symbols：

```json
{
  "action": "subscribe",
  "subscriptions": [
    {
      "topic": "crypto_prices_chainlink",
      "type": "*",
      "filters": ""
    }
  ]
}
```

保活：每 5 秒发送文本 `PING`。不要发 JSON ping，先按官方文档文本心跳。

调试要求：

- 连接后立刻订阅。
- 原样打印前 20 条 raw message 到 `runtime/rtds_debug.jsonl`。
- 至少等待 60 秒，不要 5 秒没数据就判定失败。
- 如果 Chainlink topic 无数据，马上订阅 Binance topic 验证通道是否活着：

```json
{
  "action": "subscribe",
  "subscriptions": [
    {
      "topic": "crypto_prices",
      "type": "update",
      "filters": "btcusdt,ethusdt,solusdt,xrpusdt"
    }
  ]
}
```

如果 Binance 有数据但 Chainlink 没数据：

- 采集器继续运行。
- Chainlink 状态标记为 `degraded`。
- 备用价格可以保存，但不能用于正式回测结算。

## 问题 2：btc_final 怎么精确获取

第一优先级：Polymarket RTDS Chainlink 的 `crypto_prices_chainlink`，字段：

```json
{
  "topic": "crypto_prices_chainlink",
  "type": "update",
  "timestamp": 1753314088421,
  "payload": {
    "symbol": "btc/usd",
    "timestamp": 1753314088395,
    "value": 67234.50
  }
}
```

窗口结束后：

1. 取窗口结束时间附近的 RTDS Chainlink tick。
2. 优先取 `payload.timestamp <= window_end_ms` 且最接近结束时间的一条。
3. 同时保存 `received_at`，用于判断本机延迟。
4. 计算 `calculated_winner = btc_final > ptb ? Up : Down`。
5. 最终赢家仍以平台 resolved 结果为准。

如果 RTDS Chainlink 暂时不可用：

- 可以临时使用普通 Chainlink `latestRoundData` 保存 `btc_final_fallback`。
- 字段必须叫 `btc_final_fallback`，不能冒充 `btc_final`。
- 回测报告必须把这些窗口标记为 `data_quality=estimated`。

## 问题 3：actual_winner 怎么获取

不要只依赖单一来源，按三层做：

1. CLOB WebSocket market channel
   - 订阅当前市场 Up/Down 两个 token_id。
   - 必须设置 `custom_feature_enabled: true`。
   - 监听 `market_resolved`。

2. Gamma API 轮询 closed/resolved market
   - 市场结束后每 10 秒轮询一次，持续至少 10 分钟。
   - 保存完整 market JSON 到 `resolutions.jsonl`。
   - 从 resolved/closed/outcome/winner 类字段提取 `actual_winner`。

3. 账户结果校验
   - 如果有真实订单，查询订单和持仓/赎回结果。
   - 赢的 token 最终价值 1，输的 token 价值 0。

最终字段：

```json
{
  "actual_winner": "Up",
  "winner_source": "clob_market_resolved|gamma_resolved|account_redeem|manual",
  "winner_confirmed": true,
  "settlement_mismatch": false
}
```

如果 `btc_final` 算出来的赢家和 `actual_winner` 不一致，以 `actual_winner` 为准，并保留 mismatch 标记。

## 问题 4：是否需要加 $1 market buy 滑点模拟

需要，而且必须加。否则回测会虚高。

采集器或回测器要根据当时 orderbook 模拟：

```text
用 amount=1.00 USDC 买 Up/Down：
从 best ask 开始吃单
逐档扣 available size
算 weighted average fill price
算 shares
如果盘口不够，标记 partial_fill 或 no_liquidity
```

输出字段：

```json
{
  "simulated_amount": 1.0,
  "simulated_avg_fill_price": 0.445,
  "simulated_shares": 2.24719,
  "available_liquidity_at_entry": 123.45,
  "best_ask": 0.44,
  "best_bid": 0.43,
  "spread": 0.01,
  "slippage_vs_best_ask": 0.005,
  "fill_quality": "full|partial|none"
}
```

## WebUI 现在应该接什么

新增一个“数据质量”区域，不要动实盘控制。

展示字段：

```json
{
  "collector_running": true,
  "current_market_slug": "...",
  "token_ids_ready": true,
  "clob_ws_online": true,
  "rtds_chainlink_online": true,
  "last_orderbook_tick_age_ms": 280,
  "last_price_tick_age_ms": 420,
  "current_window_tick_count": 287,
  "current_window_quality": "good|degraded|bad"
}
```

WebUI 只需要读这些状态文件或 `/api/data-quality`。不要让 WebUI 直接连 WebSocket。

## 当前优先级

1. 修通 RTDS Chainlink 订阅。
2. CLOB market channel 稳定保存 orderbook 和 best bid/ask。
3. 增加 $1 market buy 滑点模拟。
4. 增加 Gamma closed/resolved 轮询。
5. WebUI 展示数据质量。
6. 模拟盘读取新数据源跑，不碰实盘。

## Codex 对当前采集器输出的复查意见

刚看到落盘数据后，先修两个小问题：

1. `orderbook_ticks.jsonl` 里 `up.bid1_price / up.ask1_price / down.bid1_price / down.ask1_price` 现在有时是 0，但 `bids[0].price / asks[0].price` 里有真实价格。
   - 规则：保存快照时，优先用 REST book 的一档价。
   - 如果 REST book 为空，再用 WebSocket 的 `last_up_bid/last_up_ask`。
   - `spread` 必须基于最终写入的 bid1/ask1 计算。

2. `trade_ticks.jsonl` 现在写入了大量 `price_change`。
   - `price_change` 不是成交，应该写到 `orderbook_ticks.jsonl` 或新文件 `price_change_ticks.jsonl`。
   - `trade_ticks.jsonl` 只允许 `last_trade_price` 或用户订单成交事件。
   - 否则 WebUI 里的“成交tick”会虚高。

3. `market_resolved` 现在收到了不相关体育市场的事件。
   - 只有当 event 的 `condition_id` 等于当前 `current_condition_id`，或 `assets_ids/clob_token_ids` 与当前 token 匹配，才写入当前窗口的 `resolutions.jsonl`。
   - 其他市场事件写到单独 debug 文件，不要污染 BTC 5M 结算。

4. RTDS 第一批历史数组可保留，但要标注：
   - `rtds_message_kind: "snapshot"` 或 `"update"`
   - `payload_timestamp_ms`
   - `received_lag_ms = received_at_ms - payload_timestamp_ms`
