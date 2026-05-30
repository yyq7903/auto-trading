# WebUI 状态栏与盘口数据验收 1

本文件是新的指导文件，不追加到旧文档里。Hermes 读完后按这里执行并新建 `汇报2.md`。

## 用户看到的问题

截图中顶部：

```text
现价、PTB、价差、Up 都像死的
PTB 仍叫 PTB，不够直观
没有 Down
没有市场时间，例如 2026/5/26 20:00-20:05
左侧策略区下方空白太大
```

## Codex 已做的 WebUI 修复

1. `/api/status` 改为优先读取 `btc5m数据/true_market`：
   - `windows.jsonl`：开盘价、窗口开始/结束时间、PTB 质量
   - `price_ticks.jsonl`：当前官方 BTC 价格
   - `orderbook_ticks.jsonl`：Up/Down 买卖价
2. 顶部文案：
   - `PTB` 改为 `开盘价`
   - 新增 `Down`
   - 新增市场时间
3. 交易控制页左下新增 `当前市场观察` 卡片：
   - 市场时间
   - 市场编号
   - 现价
   - 开盘价
   - Up / Down
   - 数据来源和开盘价质量
   - 是否可用于观察/回测

## Hermes 必须继续修的采集器问题

### 1. 当前窗口没有正常切换

我看到 `data_quality.jsonl` 最新窗口出现：

```json
"remaining_seconds": -498
```

这说明采集器还在对已经结束的窗口继续写状态。必须修复：

```text
每秒检查当前时间
如果 now >= window_end_ts，必须切换到新的 5m 窗口
切换失败时不能继续把旧窗口标为 good
```

验收标准：

```text
remaining_seconds 必须在 300 -> 0 之间循环
不能长期为负数
```

### 2. orderbook 最新记录仍可能是空盘口

我看到最新 `orderbook_ticks.jsonl`：

```json
"up": {"bid1_price": 0, "ask1_price": 0, "bids": [], "asks": []}
```

这会让 WebUI 的 Up/Down 变成 0 或不刷新。必须修复：

1. 如果 REST `/book` 返回空，不能覆盖上一条有效盘口。
2. 保存快照时要保留 last_good_orderbook。
3. `bid1_price/ask1_price` 优先取：

```python
bids[0]["price"]
asks[0]["price"]
```

4. 如果当前 token 的盘口暂时空，数据质量要降级为 `degraded`，不能显示 `good`。

### 3. status 数据源必须保持一致

以后 WebUI 观察数据只看：

```text
/api/status
/api/data-quality
```

不要让前端直接读旧文件。旧的：

```text
btc_price.jsonl
all_events.jsonl
trader_state.json ticker
```

只能作为兜底，不作为主数据源。

## Hermes 汇报2必须包含

1. 新市场切换测试：

```json
{
  "slug": "...",
  "remaining_seconds_min": 0,
  "remaining_seconds_max": 300,
  "negative_seconds_seen": false
}
```

2. 盘口非空测试：

```json
{
  "up_bid": 0.33,
  "up_ask": 0.34,
  "down_bid": 0.66,
  "down_ask": 0.67,
  "empty_orderbook_overwrite": false
}
```

3. WebUI 顶部验收：

```text
显示：市场时间、现价、开盘价、价差、Up、Down、实盘余额
开盘价不再显示为 PTB
```

4. 不要改实盘下单逻辑，不要动 `.env`。
