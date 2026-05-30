# BTC 5m Polymarket 交易系统 — 完整移交文档 v2

> 编写日期: 2026-05-24
> 编写者: 小阿 (Hermes Agent)
> 接收者: 新任 AI

---

## 一、平台规则详解

### 1.1 Polymarket.com（国际版）基本规则

**什么是 BTC Up or Down 5m 市场？**
- 每5分钟一个窗口，预测 BTC 价格在窗口结束时相对于窗口开始时是涨还是跌
- 窗口: `btc-updown-5m-{start_unix_timestamp}`
- start_unix_timestamp = 窗口开始的秒级 Unix 时间戳（整除300）
- 例: `btc-updown-5m-1779627900` = 1779627900 开始的5分钟窗口
- 时区: UTC，每天288个窗口（24h × 12个/小时）

**结算规则:**
- 分辨率来源: Chainlink BTC/USD 数据流
- 结算方式: 窗口开始时的 BTC 价格 vs 窗口结束时的 BTC 价格
- 结束价 ≥ 开始价 → 结算为 "Up"
- 结束价 < 开始价 → 结算为 "Down"
- 结算时间: 窗口结束后约5-30秒
- 结算后 Up/Down 代币变为可赎回（redeemable），按1:1兑换 pUSD

**交易规则:**
- 代币: 每个方向一个 ERC1155 token（clobTokenIds 数组）
  - tokens[0] = Up token, tokens[1] = Down token（⚠️ 注意顺序！不要搞反）
- 价格: 买入价 = Up/Down token 的当前交易价格（0.01 ~ 0.99）
- 最小开仓: `orderMinSize` = 5 股（约 $2.50 ~ $5.00，取决于价格）
- 最小金额: 页面接受 $1，但实际最小 $2.58（5股 × 平均 $0.515）
- 费类型: `crypto_fees_v2`，taker 费率 7%，maker 返 20%
- 交易类型: FAK（Fill or Kill），FOK（Fill or Kill），GTC（Good Till Cancel）
- Polymarket.com(国际版)与polymarket.us 账户/API 完全不同，勿混淆

**平台余额机制:**
- 用户通过 Magic Link 登录，使用平台余额（Platform Balance）
- 不是链上 USDC，是 Polymarket CLOB 的信用余额
- 充值:c2a 在页面右上角点击"充值"，通过 USDC 跨链
- 签名类型: `signatureType = 3`（Proxy 代理签名）
- 充值地址: 代理钱包 `0xd2Cb39A786Bc50F782a5B5C700cF7552a108cd64`
- 注: 链上 CLOB `balance` endpoint 返回 0（因为余额不是链上资产）

### 1.2 CLOB API 下单格式

完整 POST 请求到 `https://clob.polymarket.com/order`:

```json
{
  "deferExec": false,
  "postOnly": false,
  "order": {
    "salt": 随机数,
    "maker": "代理钱包地址",
    "signer": "代理钱包地址",
    "tokenId": "token ID (十进制字符串)",
    "makerAmount": "1000000",
    "takerAmount": "1010100",
    "side": "BUY",
    "signatureType": 3,
    "timestamp": "毫秒时间戳",
    "expiration": "0",
    "metadata": "0x0000...",
    "builder": "0x0000...",
    "signature": "EIP-712 签名十六进制"
  },
  "owner": "poly_api_key",
  "orderType": "FAK"
}
```

说明:
- `makerAmount`: 付出金额（1 USDC = 1000000，6位小数）
- `takerAmount`: 期望收入金额（通常 = makerAmount × (1+费率)）
- `salt`: 随机数，防止重放攻击
- `timestamp`: 毫秒级 Unix 时间戳
- `signature`: EIP-712 签名，由代理钱包私钥生成（不可伪造）
- `owner`: CLOB API key ID
- `orderType`: "FAK" = Fill or Kill

响应格式（成功）:
```json
{
  "errorMsg": "",
  "orderID": "0x6eb21a58...",
  "takingAmount": "1.0309",
  "makingAmount": "0.999973",
  "status": "matched",
  "transactionsHashes": ["0x841ab7d4..."],
  "success": true
}
```

### 1.3 CLOB API 认证头（四层验证）

第一层 — `poly_signature` HMAC（HTTP 请求认证）
```
secret = base64_decode(api_secret)
message = timestamp + method + requestPath + body
signature = base64(HMAC-SHA256(secret, message))
```
Python 代码:
```python
import hmac, hashlib, base64
secret_decoded = base64.urlsafe_b64decode(api_secret)
message = timestamp + method + path + body.replace("'", '"')
sig = hmac.new(secret_decoded, message.encode(), hashlib.sha256).digest()
sig_b64 = base64.urlsafe_b64encode(sig).decode()
```

第二层 — `owner` 字段匹配 `poly_api_key` header
第三层 — order 中 `signer` 地址匹配 API key 所有者地址
第四层 — order 中 EIP-712 `signature` 验证（不可绕过）

### 1.4 Token ID 格式

- gamma API 的 `clobTokenIds` 字段是**十进制字符串**
  ```json
  "clobTokenIds": ["77560431632102880141225683633423747058402088434698212094021560173233946167440", "51973075492152766792741256372373337822501796358250815132131881147075240387849"]
  ```
- tokens[0] = Up, tokens[1] = Down
- CLI `markets get <slug>` 返回的 `clobTokenIds` 是十进制格式
- `outcomePrices` 对应 Up/Down 价格: `["0.515", "0.485"]`

---

## 二、策略详解

### 2.1 策略一（默认，当前使用）

```
entry_second: 25        // T-25s 到 T-5s 入场
gap_threshold: 10       // gap ≥ $10 才入场
min_buy_price: 0.60     // 不买低于 60¢ 的 token
bet_fraction: 1.0       // 全仓下注
```

**完整工作流:**

1. 每个5分钟窗口，在 T-25s ~ T-5s 期间检查
2. 通过 Chainlink RPC 读当前 BTC 价格（`get_btc_fresh()`）
3. 通过 `fetch_ptb(slug)` 获取窗口起始 BTC 价格（第一次调用时缓存）
4. 计算 `gap = current_btc - window_start_btc`
5. if gap ≥ $10 → buy Up（期望 BTC 继续涨）
6. if gap ≤ -$10 → buy Down（期望 BTC 继续跌）
7. 买入 token 的价格：从市场数据中读取该方向的最新价格
8. if 买入价格 < min_buy_price → 跳过（价格太差）
9. 下注金额: `bankroll × bet_fraction`（当前全仓 $3.35）
10. 等待结算（窗口结束+5秒）
11. 检查结算结果，记录盈亏

### 2.2 策略为何这样设计

**为什么 gap ≥ $10 才入场？**
- 回测数据（511 个市场，720 种组合）:
  - T-10s gap ≥ $50 → 100% 胜率, Sharpe 4.07
  - T-10s gap ≥ $30 → 99.6% 胜率
  - T-25s gap ≥ $30 → 96.2% 胜率
  - T-25s gap ≥ $10 → 88.5% 胜率
- gap 越大胜率越高，因为 BTC 的动量会在5分钟内延续
- 阈值 $10 是平衡了胜率和交易频率的选择

**为什么 T-25s ~ T-5s 入场？**
- 太早（> T-30s）：gap 可能还没形成，浪费机会
- 太晚（< T-5s）：市场即将关闭，流动性下降，可能无法成交
- T-25s ~ T-5s 是流动性和信号质量的平衡点

**为什么方向是 gap 的方向？**
- 动量效应: 如果 BTC 在窗口前25分钟涨了 $10，说明有上涨动力
- 这个动量在剩余5分钟内大概率持续
- 不是反向交易——不要赌"涨太多了该跌了"

### 2.3 策略验证举例

假设 BTC 当前 $76,500:
```
窗口开始: 1779627900 (13:00 UTC)
窗口起始 BTC: $76,400 (从 Chainlink 读取)
在 T-25s (13:04:35 UTC):
  BTC 当前: $76,420
  gap = $76,420 - $76,400 = $20
  gap ≥ $10 ✅
  方向: Up
  买入 Up token @ ~$0.55
  投入: $3.35 → 买入约 6 股
在 13:05:00 UTC 结算:
  BTC 结束价: $76,430
  $76,430 ≥ $76,400 → Up ✅
  每股回收: $1.00
  总收入: 6 × $1.00 = $6.00
  利润: $6.00 - $3.35 = $2.65 (+79%)
```

假设 BTC 当前 $76,500:
```
窗口开始: 1779627900
窗口起始 BTC: $76,400
在 T-25s:
  BTC 当前: $76,385
  gap = $76,385 - $76,400 = -$15
  gap ≤ -$10 ✅
  方向: Down
  买入 Down token @ ~$0.40
  投入: $3.35 → 买入约 8 股
结算:
  BTC 结束价: $76,390
  $76,390 ≥ $76,400 → Up ❌
  每股回收: $0
  总亏损: -$3.35 (-100%)
```

### 2.4 可选策略（config.json 中配置）

| 策略 | entry | gap | min_price | 下注比例 | 回测胜率 |
|---|---|---|---|---|---|
| 1 (默认) | 25s | $10 | 0.60 | 100% | 95.4% |
| 2 (稳健) | 10s | $50 | 0.55 | 50% | 100.0% |
| 3 (高收益) | 10s | $20 | 0.60 | 100% | 99.7% |
| 4 (平衡) | 15s | $30 | 0.65 | 50% | 99.2% |
| 5 (保守) | 20s | $30 | 0.70 | 25% | 98.9% |

注: 胜率是回测5月23日数据的结果，实际可能不同

---

## 三、系统详细配置

### 3.1 Chrome Profile

路径: `C:\temp\chrome-profile-bot`
- 已登录 Polymarket（Magic Link session）
- 登录方式: Google OAuth + Magic Link
- 登录邮箱: `yyq7903@gmail.com`
- localStorage 关键键值:
  - `polymarket.auth.proxyWallet`: `0xd2Cb39...`
  - `polymarket.auth.cache.account`: `{"137":"0x8aa26B55..."}`
  - `poly_clob_api_key_map`: API 凭证（含 secret）
  - `polymarket.auth.params`: Magic Link 认证参数

⚠️ 注意: 
- Playwright 使用 `launch_persistent_context` 启动，不创建新 profile
- Chrome 关闭后 profile 仍保存
- 如果 Chrome 异常关闭，可能会锁定 profile，需要等几秒再启动

### 3.2 .env 文件

路径: `/mnt/c/Users/yyq/Desktop/自动交易/btc5m-trader/.env`
```
PRIVATE_KEY=7421a7634d5850b62c63db6782013b6a7d7faa5097e38fe1bbc0184a143351c9
FUNDER_ADDRESS=0x23D779628967Db6D8896031a8Cdf739A9273d201
```

说明:
- PRIVATE_KEY: Funder 私钥（对应地址 `0x5d1F53...`）
- 这个私钥不能直接用于下单（不是代理钱包密钥）
- 用途: CLI auth, HMAC 签名, API 凭证生成
- FUNDER_ADDRESS: 出金地址

### 3.3 CLI 补丁详情

**修改文件清单:**
| 文件 | 修改内容 |
|---|---|
| `src/config.rs` | 加 `POLYMARKET_FUNDER` env var、`resolve_funder()`、Config.funder |
| `src/auth.rs` | `authenticated_clob_client()` 和 `authenticate_with_signer()` 加 funder 参数 |
| `src/main.rs` | Cli 结构体加 `--funder` 参数，传递给 clob 命令 |
| `src/commands/clob.rs` | 解析 funder → 传递给所有 auth 调用 |

**补丁代码的关键改动（auth.rs）:**
```rust
pub async fn authenticate_with_signer(
    signer: &(impl polymarket_client_sdk_v2::auth::Signer + Sync),
    signature_type_flag: Option<&str>,
    funder: Option<&str>,
) -> Result<clob::Client<Authenticated<Normal>>> {
    let sig_type = parse_signature_type(&config::resolve_signature_type(signature_type_flag)?);
    let mut builder = unauthenticated_clob_client()?
        .authentication_builder(signer)
        .signature_type(sig_type);
    if let Some(f) = funder {
        let addr = Address::from_str(f)
            .map_err(|_| anyhow::anyhow!("Invalid funder address: {f}"))?;
        builder = builder.funder(addr);
    }
    builder.authenticate().await
        .context("Failed to authenticate with Polymarket CLOB")
}
```

**编译:** 从 `suhail/clob-v2` 分支构建
```bash
cd /tmp/polymarket-cli
git checkout suhail/clob-v2
cargo build --release
cp target/release/polymarket ~/.local/bin/
```

---

## 四、数据库和日志

### 4.1 交易记录格式

`trades.jsonl`（每行一个 JSON）:
```json
{
  "time": "2026-05-24T20:47:04",
  "slug": "btc-updown-5m-1779626700",
  "direction": "Up",
  "gap": 12.34,
  "btc_entry": 77000.00,
  "ptb": 76987.66,
  "amount": 1.0,
  "orderID": null,          // 成交后有值
  "status": "skipped",      // 或 "matched", "failed"
  "makingAmount": null,
  "takingAmount": null,
  "txHashes": null,
  "mode": "live"
}
```

`skipped` 格式:
```json
{
  "time": "...",
  "slug": "btc-updown-5m-...",
  "mode": "live",
  "direction": "none",
  "gap": 0,
  "btc_entry": 0,
  "buy_price": 0,
  "seconds_left": 80,
  "status": "skipped",
  "skip_reason": "价差$0<$10"
}
```

### 4.2 策略运行日志

`/tmp/strategy_watch.log`:
```
[23:45:24] 策略测试启动 — Chainlink ptb + Executor
[23:45:24] ❤️ 运行中 slug=btc-updown-5m-1779637500 剩余=276s session活跃
[23:47:34] btc-updown-5m-1779637500 gap=$+0.00 Up 剩余25s
[23:47:34] ⏭ gap $0 < $10, 跳过
```

### 4.3 Executor 日志

`C:\temp\debug\executor_log.txt`:
```
[INIT] 23:30:30 启动浏览器...
[INIT] 23:30:31 ✅ Chrome 就绪
[QUEUE] 23:30:40 📨 处理订单: btc-updown-5m-1779637500 Down $1
[NAV] 23:30:41 导航: https://polymarket.com/zh/event/btc-updown-5m-...
[AMT] 23:30:48 填金额 $1: True
[CLICK] 23:30:49 ✅ 点击: 买入 Down
[REQ] 23:31:06 📤 请求: POST https://clob.polymarket.com/order
[CLOB] 23:31:06 ✅ clob 响应: 200 status=matched orderID=0x6eb21a58...
```

---

## 五、完整已测试清单

### ✅ 正面测试（全部通过）

| 测试项 | 结果 | 备注 |
|---|---|---|
| CLI `markets get <slug>` | ✅ | 返回完整市场数据 |
| CLI `clob account-status -o json` | ✅ | `closed_only: false` |
| CLI `clob api-keys -o json` | ✅ | 返回 2 个 API key |
| CLI `clob orders -o json` | ✅ | 返回空列表 |
| CLI `clob balance --asset-type collateral -o json` | ✅ | 返回 0（因为平台余额不是链上资产）|
| CLI `data positions <address> -o json` | ✅ | 返回持仓 |
| CLI `wallet show -o json` | ✅ | 显示地址/代理地址/签名类型 |
| CLI `--funder` 参数 | ✅ | 解析并传递给 SDK |
| `POLYMARKET_FUNDER` env var | ✅ | 环境变量生效 |
| Playwright 导航到市场页 | ✅ | 20s timeout |
| Playwright 填金额 | ✅ | React 受控组件：nativeSetter + dispatchEvent |
| Playwright 点击买入按钮 | ✅ | `page.evaluate()` 找 button.trading-button |
| Magic Link 签名（通过 UI 交互）| ✅ | 真实下单成功 |
| CLOB 下单 POST | ✅ | 返回 orderID + matched |
| Chainlink RPC 读 BTC 价格 | ✅ | Polygon 合约 `0xc907E1...` |
| `fetch_ptb()` 缓存机制 | ✅ | 每个 slug 首次记录，窗口内不变 |
| executor 队列模式 | ✅ | 主线程处理，子线程入队 |
| 页面余额读取 | ✅ | 从 `$X.XX` 文本提取 |
| 本地存储 API 凭证提取 | ✅ | `poly_clob_api_key_map`|
| HMAC auth header 生成 | ✅ | 用 api_secret 签名 |

### ❌ 负面测试（全部不可行）

| 测试项 | 结果 | 原因 |
|---|---|---|
| CLI `create-order` | ❌ | EIP-712 签名不可伪造 |
| CLI `market-order` | ❌ | 同上 |
| py-clob-client `create_market_order` | ❌ | "Invalid order inputs" |
| py-clob-client 带 funder 下单 | ❌ | "signer 地址不匹配" |
| postMessage → Magic iframe | ❌ | 无响应（跨域 + 通道绑定）|
| `window.__webpack_require__` | ❌ | Turbopack 不暴露 |
| `window.ethereum` | ❌ | 页面不存在 |
| `window.magic` | ❌ | 不存在 |
| React fiber 遍历 | ❌ | 50000 节点未找到 wagmi |
| form.requestSubmit() | ❌ | React 18 不响应 |
| 按钮 dispatchEvent | ❌ | React 合成事件不触发签名 |
| gamma API `priceToBeat` | ❌ | 字段已永久消失 |
| 余额不足时 "买入 Up" 按钮 | ❌ | 变为"充值"或"暂无卖单" |
| 剩余 < 60s 的窗口 | ❌ | 按钮可能隐藏或不可用 |
| 默认 Python SDK (v1) | ❌ | 不支持 signatureType=3 |

---

## 六、已知问题和限制

### 6.1 运行中问题

1. **响应捕获超时**: Magic Link 签名需要 ~15s，等待循环设为30s
2. **余额显示**: CLI `clob balance` 返回 0，平台余额只能从页面读
3. **多窗口调度**: `fetch_ptb()` 在 slug 变化时自动记录新 ptb，但第一次调用可能返回前一个窗口的缓存
4. **连续多个窗口无 gap**: BTC 横盘时可能连续几个小时无信号

### 6.2 架构限制

1. **Playwright 只能在主线程**: HTTP 子线程调用报 greenlet error
2. **Windows 依赖**: executor 必须跑在 Windows（Chrome profile 在 Windows 上）
3. **Chrome 必须保持登录**: session cookie 过期后需要重新登录
4. **WSL ↔ Windows 通信**: 通过 `172.18.16.1:8789` WSL 网关 IP
5. **无法纯后端下单**: EIP-712 签名必须通过浏览器内的 Magic Link

### 6.3 安全注意事项

1. **私钥明文存储**: `.env` 文件包含私钥，不要泄露
2. **API 凭证暴露**: `poly_clob_api_key_map` 包含 api_secret，不要写入日志
3. **Chrome profile**: 含登录 session，不要删除
4. **Magic Link session**: 有效期未知，可能需要定期重新登录

---

## 七、快速启动指南

### 启动顺序

```
1. 启动浏览器执行器（Windows）
   双击 C:\temp\启动浏览器执行器.bat
   或: python C:\temp\browser_executor_server.py
   验证: curl http://localhost:8789/heartbeat

2. 启动 WebUI（WSL，可选）
   cd /mnt/c/Users/yyq/Desktop/自动交易/btc5m-webui && python3 api_server.py &
   打开: http://localhost:8877

3. 启动策略监控（WSL）
   cd /mnt/c/Users/yyq/Desktop/自动交易/btc5m-trader
   PYTHONUNBUFFERED=1 python3 -u strategy_test.py

4. 查询验证（WSL）
   polymarket markets get btc-updown-5m-{ts} -o json
```

### 日常检查命令

```bash
# 策略进程状态
ps aux | grep strategy_test | grep -v grep

# Executor 状态
curl -s http://172.18.16.1:8789/heartbeat

# 最新成交
tail -3 /mnt/c/Users/yyq/Desktop/自动交易/btc5m数据/trades.jsonl

# 余额（从页面读，不是 CLI）
# 打开 http://localhost:8877 查看

# 账户当前持仓
export PRIV_KEY=$(grep PRIVATE_KEY /path/to/.env | cut -d= -f2)
polymarket --private-key $PRIV_KEY --sig-type proxy --funder 0xd2Cb39... data positions 0xd2Cb39... -o json

# 未成交订单
polymarket --private-key $PRIV_KEY --sig-type proxy --funder 0xd2Cb39... clob orders -o json

# 检查 cronjob 状态
cronjob action=list
```

---

## 八、向新手 AI 的特别说明

### 最重要的三件事

1. **永远不要不按策略下单** — 上一次犯了这错，用户亏了钱，非常生气
2. **Magic Link 不可绕过** — 没有技术方式能导出代理钱包私钥，只能通过 Playwright + UI
3. **CLI 是查询工具不是下单工具** — 已加 `--funder` 补丁，但`create-order`仍然不可用

### 文件索引

```
/mnt/c/Users/yyq/Desktop/自动交易/btc5m-trader/           → 策略代码
  ├── strategy_test.py                       → 当前运行的策略监控
  ├── live/trader.py                         → 旧版 trader（待合并）
  ├── shared/btc_price.py                    → BTC 价格 + ptb 逻辑
  ├── shared/config.py                       → 配置管理
  ├── live/config.json                       → 策略参数
  ├── .env                                   → 私钥
  ├── browser_executor/__init__.py           → WSL→Windows HTTP 客户端
  ├── sim/trader.py                          → 模拟交易器
  └── HANDOFF.md                             → 本文件

C:\temp\                                      → Windows 执行器
  ├── browser_executor_server.py              → Playwright 服务
  ├── executor_launcher.py                    → 自动保活（旧）
  ├── chrome-profile-bot\                     → Chrome 配置
  └── debug\                                  → 日志

/home/yyq/.local/bin/polymarket              → CLI（已打补丁）
/tmp/polymarket-cli/                         → CLI 源码
/mnt/c/Users/yyq/Desktop/自动交易/btc5m-webui/              → WebUI
```

### 当前状态（移交时）

- strategy_test.py: **运行中**（PID 65399），监控窗口
- executor: **运行中**（:8789），等待请求
- CL: **已打 --funder 补丁**
- 余额: **$3.35** pUSD
- 已成交: **1 笔**（由之前未按策略的测试产生，用户已卖出）
- 当前 cronjob: **运行中**（每15分钟汇报一次）
