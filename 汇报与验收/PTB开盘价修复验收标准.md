# PTB 开盘价修复验收标准

用户反馈的例子：

```text
市场：btc-updown-5m-1779793200
平台 Price to Beat：77343.67
WebUI 显示 PTB：77369.98
```

这不是小误差，是取值逻辑错了。必须暂停把这个当成“可接受误差”。

## 根因

当前采集器不应该在 `switch_market()` 里用“当前最新 RTDS 价格”当 PTB。

错误逻辑：

```python
ptb = last_rtds_price
```

原因：采集器切换市场、Gamma API 返回市场、WebSocket 收到第一条 tick 都可能比真实窗口开始时间晚几秒到几十秒。BTC 5 分钟市场里几十美元偏差很常见，所以这会直接毁掉模拟盘和回测。

也绝对不能用 CLOB 盘口 ask/bid 推断 PTB。盘口价格是 Up/Down 概率，不是 BTC 开盘价。

## 正确 PTB 定义

对 BTC 5M：

```text
PTB = 当前 5 分钟窗口开始时间 window_start_ts 对应的 Polymarket RTDS Chainlink BTC/USD 数据流价格
```

如果拿不到精确同秒，则取：

```text
payload.timestamp <= window_start_ms
且最接近 window_start_ms 的 btc/usd tick
```

不要取 `>= window_start_ms` 的下一条，除非用字段标记 `ptb_quality=estimated_after_boundary`，并且该窗口不能进入正式回测。

## 第一修复方案：用本地 RTDS tick 环形缓存

采集器必须维护最近至少 10 分钟的 Chainlink RTDS tick：

```python
rtds_ticks = deque(maxlen=1200)

{
  "symbol": "btc/usd",
  "timestamp_ms": 1779793200000,
  "value": 77343.67,
  "source": "polymarket_rtds_chainlink",
  "message_type": "subscribe|update"
}
```

切换市场时：

```python
def select_ptb_from_rtds(window_start_ms):
    candidates = [
        t for t in rtds_ticks
        if t["symbol"] == "btc/usd" and t["timestamp_ms"] <= window_start_ms
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda t: t["timestamp_ms"])
```

保存字段：

```json
{
  "ptb": 77343.67,
  "ptb_source": "polymarket_rtds_chainlink",
  "ptb_timestamp_ms": 1779793200000,
  "ptb_window_start_ms": 1779793200000,
  "ptb_lag_ms": 0,
  "ptb_quality": "exact"
}
```

质量标准：

```text
abs(ptb_timestamp_ms - window_start_ms) <= 1000  => exact
<= 3000                                         => close
> 3000 或用了 window_start 后的 tick             => bad，不进正式回测
```

## 第二修复方案：平台页面校验

对每个已经生成的市场，采集器或校验脚本必须抓一次平台页面：

```text
https://polymarket.com/zh/event/{slug}
```

解析文本：

```text
Price to Beat（$77,343.67）
```

或中文页面中的：

```text
开盘"Price to Beat"（$77,343.67）
```

用途：

1. 作为验收校验。
2. 对已结束市场回填 `platform_ptb`。
3. 若 `abs(ptb - platform_ptb) > 1`，该窗口标记：

```json
{
  "ptb_mismatch": true,
  "data_quality": "bad",
  "exclude_from_backtest": true
}
```

注意：页面校验可以慢一点，不用于实时交易入场；实时交易用 RTDS tick 缓存。

## 必须修掉的现有代码点

在 `btc5m-trader/collectors/true_market_collector.py`：

1. `switch_market()` 中删除：

```python
current_price = last_rtds_price if last_rtds_price > 0 else 0
...
ptb = current_price
```

2. 禁止 fallback 到：

```python
up_book["asks"][0]["price"]
```

这是概率，不是 BTC 价格。

3. `on_rtds_message()` 每解析一条 Chainlink tick，都必须写入内存 ring buffer，不只是写 jsonl。

4. 新窗口切换时，如果没有窗口开始前的 RTDS tick：

```text
不要创建正式窗口
不要跑模拟盘
标记等待 PTB
```

## WebUI 显示要求

WebUI 不要只显示 `PTB $xx`，要显示来源和质量：

```text
开盘价 $77,343.67
来源：平台官方价格流
质量：精确 / 接近 / 异常
与平台页面差值：$0.00
```

如果质量不是 `exact/close`，WebUI 要显示：

```text
本窗口数据不准，不参与正式回测
```

## 验收方法

Hermes 修完后，必须用这三个市场验收：

```text
btc-updown-5m-1779793200
至少再取 2 个新结束市场
```

每个市场输出：

```json
{
  "slug": "btc-updown-5m-1779793200",
  "our_ptb": 77343.67,
  "platform_ptb": 77343.67,
  "diff": 0.0,
  "ptb_timestamp_ms": 1779793200000,
  "window_start_ms": 1779793200000,
  "ptb_quality": "exact",
  "pass": true
}
```

合格标准：

```text
abs(our_ptb - platform_ptb) <= 1.00
```

超过 1 美元的窗口不允许进入正式回测。
