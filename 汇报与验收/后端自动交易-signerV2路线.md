# 后端自动交易 signerV2 路线

目标：摆脱 Magic Link、网页点击、浏览器托管钱包，改成后端直接用 MetaMask 自有 signer + Polymarket CLOB v2 SDK 自动交易。

状态：本文档给 Hermes 接手实现。当前 WebUI 不开放实盘武装；实盘按钮只展示连接状态。

## 参考源

- Polymarket Deposit Wallets: https://docs.polymarket.com/trading/deposit-wallets
- Polymarket Trading Overview: https://docs.polymarket.com/trading/overview
- Python CLOB v2 SDK: https://github.com/Polymarket/py-clob-client-v2
- Rust CLOB v2 SDK: https://github.com/Polymarket/rs-clob-client-v2
- 相关错误复现：`maker address not allowed, please use the deposit wallet flow`
  https://github.com/Polymarket/py-clob-client-v2/issues/53

## 官方关键事实

1. 新 API 用户通常走 Deposit Wallet flow。
2. Deposit Wallet 订单使用 `signature_type = 3`，也叫 `POLY_1271`。
3. Deposit Wallet 下单时，CLOB order 的 `maker` 和 `signer` 都必须是 deposit wallet 地址。
4. pUSD 必须在 deposit wallet 地址里；EOA 自己的钱包余额不等于 deposit wallet 买入力。
5. 更新 CLOB balance/allowance 时也要使用 `signature_type = 3`。
6. 市价单本质是立即成交限价单：
   - `FOK`：全部立即成交，否则取消。
   - `FAK`：能成交多少成交多少，剩余取消。

## 2026-05-26 现状结论

当前后端路线不要先给 `0x5d1F53...` 充值后再赌 Route A。

原因：

1. `py-clob-client-v2` issue #53 已有人用全新 EOA 在 Polygon mainnet 复现：basic EOA flow 会被 CLOB 拒绝，错误就是 `maker address not allowed, please use the deposit wallet flow`。
2. 官方 Deposit Wallet 文档明确写了新 API 用户的订单签名类型是 `3 / POLY_1271`，order maker 和 signer 都是 deposit wallet address。
3. 官方文档还明确写了 pUSD 必须在 deposit wallet 地址里；EOA 持有的 pUSD 不会算作 deposit wallet 订单的 CLOB 买入力。
4. 所以 `0x5d1F53...` 当前 CLOB balance 为 0 不是唯一问题。即使给它转 pUSD，也很可能继续被主网 CLOB 拒绝。

当前建议：

- Route A 只保留为实验，不作为主路线。
- 主路线直接切 Route B：MetaMask owner signer + Deposit Wallet + Relayer + `signature_type=3`。
- 旧 Magic Link 代理钱包的 $3.35 不要强行迁到 EOA 测试；更干净的方式是新建后端专用 MetaMask EOA，部署/派生它自己的 deposit wallet，再给该 deposit wallet 充最低测试资金。

## 路线选择

### 路线 A：MetaMask EOA 直连 CLOB

适合条件：Polymarket 后端允许该地址作为普通 EOA maker。

风险：截至 2026-05-26，主网很可能已经不再允许新 EOA 直接下单。GitHub issue #53 的复现与我们当前报错一致。

步骤：

1. 新建或指定一个 MetaMask 钱包。
2. 导出私钥，只放入本机 `.env`，不要写入日志。
3. 安装 `py-clob-client-v2`。
4. 用 EOA 私钥创建/派生 CLOB API key。
5. 初始化 `ClobClient(host, chain_id=137, key=PRIVATE_KEY, creds=ApiCreds(...), signature_type=0)`。
6. 调用 `get_balance_allowance` 检查 pUSD 余额和 allowance。
7. 调用 `update_balance_allowance`。
8. 用小额订单测试：
   - 先 `create_market_order(..., dry-run/log only)`。
   - 再 `create_and_post_market_order(..., order_type=FAK)`。
9. 如果报 `maker address not allowed`，说明该地址不能走 EOA 直连，切路线 B。

Route A 的充值判断：

- 只有在确认该 EOA 真实下单不会被 `maker address not allowed` 拦截后，才值得继续给该地址增加更多测试资金。
- 如果只是为了验证，充值金额应低于或等于平台最低下单金额 + 极小余量。
- 不需要为了 gas 先买 MATIC；官方 relayer/gasless 路线覆盖钱包部署、approve、CTF 操作和 transfer。EOA 直连是否需要 gas 取决于你是否做链上 approve/transfer，但最终主路线不应该依赖 EOA gas。

### 路线 B：MetaMask Owner Signer + Deposit Wallet

这是当前官方更稳的后端路线，不依赖 Magic Link，也不依赖网页点击。

步骤：

1. 用 MetaMask EOA 作为 owner signer。
2. 安装：
   - Python: `py-builder-relayer-client`, `py-clob-client-v2`
   - 或 TypeScript: `@polymarket/builder-relayer-client`, `@polymarket/clob-client-v2`, `@polymarket/builder-signing-sdk`, `viem`
3. 配置 builder/relayer API 凭证：
   - `BUILDER_API_KEY`
   - `BUILDER_SECRET`
   - `BUILDER_PASS_PHRASE`
   - `RELAYER_URL`
   - `CLOB_API_URL=https://clob.polymarket.com`
   - `CHAIN_ID=137`
   
   Relayer API Key 来源：Polymarket 网站 `Settings > API Keys`。官方说明 relayer 使用 `RELAYER_API_KEY` 和 `RELAYER_API_KEY_ADDRESS`，已有 builder signing key 时可以继续用于 relayer。
4. 派生并部署 deposit wallet：
   - Python: `relayer.get_expected_deposit_wallet()`
   - Python: `relayer.deploy_deposit_wallet()`
5. 将 pUSD 转入 deposit wallet，而不是只放在 MetaMask EOA。
   - 小额测试推荐直接用 Polymarket 官方 deposit / Bridge API 给 deposit wallet 充值。
   - Polymarket deposit 文档说明支持从多链存入资产，并自动换成 Polygon 上的 pUSD。
   - 注意每个资产有最低充值额，需先查 `/supported-assets`。
6. 从 deposit wallet 发起 approve：
   - ERC20 pUSD approval
   - 必要时 ERC1155 conditional token approval
   - approve calldata 通过 relayer `WALLET` batch 提交。
7. 初始化 CLOB v2：
   - `signature_type = SignatureTypeV2.POLY_1271` 或数值 `3`
   - `funder = DEPOSIT_WALLET`
   - `key = PRIVATE_KEY`
   - `creds = ApiCreds(CLOB_API_KEY, CLOB_SECRET, CLOB_PASS_PHRASE)`
8. 调用：
   - `clob.update_balance_allowance(asset_type=COLLATERAL, signature_type=3)`
   - `clob.get_balance_allowance(...)`
9. 订单执行：
   - 获取当前 BTC 5m slug。
   - 从 Gamma/collector 拿 Up/Down token id。
   - 从 CLOB orderbook 计算 ask / 可成交深度。
   - 用 `MarketOrderArgs(token_id, amount, Side.BUY, order_type=FAK)`。
   - `create_and_post_market_order(..., order_type=FAK)`。
10. 写入 `btc5m数据/trades.jsonl`，字段与 WebUI 表格保持一致。

## 项目落地结构建议

```text
btc5m-trader/
  backend_executor/
    __init__.py
    config.py
    wallet.py          # EOA / deposit wallet / relayer
    clob.py            # CLOB v2 client 初始化、余额、allowance、订单
    orderbook.py       # 深度、滑点、FAK/FOK 可成交检查
    runner.py          # 被 live trader 调用
  live/
    trader.py          # 策略触发后调用 backend_executor
```

## 必做验收

1. `health` 能返回：
   - signer address
   - deposit wallet address
   - CLOB API key 对应地址
   - pUSD balance
   - allowance
   - signature type
2. dry-run 能根据 token id 计算市场单价格，不提交订单。
3. 小额 `$1 FAK` 真实订单返回 `matched` 或明确的 CLOB 错误。
4. 所有错误写入 `trades.jsonl`，并在 WebUI 最近交易里显示原因。
5. 后端完整跑通后，WebUI 才开放实盘启动按钮；仍不需要旧的确认码武装。

## 当前已知坑

- 当前 Magic 账号导出的私钥地址和网页 API key 绑定地址不一致，因此 SDK 会报 `the order signer address has to be the address of the API KEY`。
- 使用旧 `FUNDER_ADDRESS=0x23D...` 会显示 CLOB balance 为 0，因为那是出金地址，不是可下单钱包。
- 当前项目能成交的路径是浏览器 Magic session；这是临时可用路线，不是最终后端路线。
- `py-clob-client` 旧版不要再用，使用 `py-clob-client-v2`。

## 对当前 PRIVATE_KEY 的判断

当前 `.env` 的 `PRIVATE_KEY` 对应地址是 `0x5d1F53...`。从错误表现看：

- 它不是当前网页 Magic 代理钱包 `0xd2Cb39...` 的私钥。
- 它也不是网页 `poly_clob_api_key_map` 里当前 CLOB API key 绑定的 signer 地址。
- 它更像旧项目里用于 CLI/HMAC/辅助认证的 EOA 私钥，或旧 Magic 流程中的外部 owner/funder 地址。

是否“在 Polymarket 注册过”不能只看本地文件判断。验收方法：

1. 用该私钥派生 CLOB API key。
2. 调 `account-status` / `get_closed_only_mode`。
3. 用小额 dry-run 后做真实 `FAK`。
4. 如果真实提交返回 `maker address not allowed`，就视为该地址不能走 Route A。

但因为已有公开复现显示新 EOA 主网会报同样错误，Hermes 应优先做 Route B。

## 2026-05-26 Route B 新突破

Hermes 已经通过 CLOB API 创建 Builder API Key，并用 relayer 派生出 deposit wallet：

- Owner signer：`0x5d1F53...93CC3c`
- Deposit wallet / funder：`0x23D779628967Db6D8896031a8Cdf739A9273d201`
- Relayer URL：`https://relayer-v2.polymarket.com/`

Codex 独立核对 Polygon mainnet：

- `eth_getCode(0x23D779...)` 返回非空合约代码，不是 EOA。
- 合约代码末尾包含 owner `0x5d1F53...93CC3c`，说明该地址确实是 owner 对应的 deposit wallet。
- `eth_getBalance(0x23D779...) = 0`，但这不阻碍 gasless relayer。
- pUSD balance 为 0。

结论：

- `deploy_deposit_wallet()` 报 `wallet already deployed` 是正常信号：这个 deposit wallet 已部署。
- 不需要“强制重新部署”，也不需要换 owner。
- 不要往 deposit wallet 转 MATIC 作为 gas；官方 gasless relayer 会为 wallet deployment、approve、CTF 操作和 transfer 付 gas。
- 下一步不是 deploy，而是 funding + approval + CLOB balance sync。

Hermes 下一步顺序：

1. 立即轮换 Builder API Key。
   - 原因：key/passphrase 已经出现在对话文本里，不应作为长期凭证。
   - 新 key 写入本地 `.env`，不要再贴全文。
2. 确认 deposit wallet 地址：
   - `relayer.get_expected_deposit_wallet()` 必须仍然返回 `0x23D779...`。
   - `eth_getCode` 必须非 `0x`。
3. 给 deposit wallet 充值 pUSD。
   - 收款地址使用 `0x23D779...`。
   - 推荐走 Polymarket 官方 deposit / Bridge API 或网页充值到该 deposit wallet。
   - 如果直接链上转账，确认转的是 Polygon pUSD 正确合约，不是 USDC.e 或其他资产。
4. 查询 pUSD balance。
   - pUSD token 地址可从官方 Contracts 文档核对。
   - balance > 最低下单金额后再继续。
5. 通过 relayer `WALLET` batch 从 deposit wallet 做 approval。
   - approval 必须由 deposit wallet 发起，不是 owner EOA。
   - 需要 fresh `WALLET` nonce。
6. 调 CLOB：
   - `update_balance_allowance(asset_type=COLLATERAL, signature_type=3)`
   - `get_balance_allowance(asset_type=COLLATERAL, signature_type=3)`
7. 做 `$1 FAK` 小额真实单。

主网 vs staging：

- 主网资金、Polygon mainnet、真实 BTC 5m 交易，只能用 `https://relayer-v2.polymarket.com/`。
- `relayer-v2-staging.polymarket.dev` 是 staging/test 环境，401 很可能是没有 staging builder/relayer key；不要拿主网 key 去试 staging。
- 现在既然主网 relayer 能返回确定的 wallet 状态，就继续主网路线。

## GitHub 成熟项目判断

结论：有可参考项目，但没有一个建议不审计、不改造就直接拿来跑真钱。

### 1. 官方 SDK：必须作为执行层底座

- `Polymarket/py-clob-client-v2`
- `Polymarket/clob-client-v2`
- `Polymarket/rs-clob-client-v2`

用途：

- CLOB v2 订单、余额、allowance、订单簿。
- Deposit wallet / builder / relayer 官方类型和签名结构。
- 这是后端自动交易的核心依赖，不要绕开。

### 2. discountry/polymarket-trading-bot

地址：https://github.com/discountry/polymarket-trading-bot

可借鉴：

- Python 项目结构清晰。
- 支持 gasless / Builder Program credentials。
- 有 CLOB + Relayer API client、WebSocket orderbook、策略目录、TUI、测试。
- 支持 BTC/ETH/SOL/XRP 15m Up/Down，可改成 5m。

不能直接拿来跑的原因：

- 默认策略不是我们的 BTC 5m 策略一。
- 文档偏 safe/proxy 旧称，需要核对是否完全符合 2026 CLOB v2 deposit wallet flow。
- 需要适配我们已有 collector、WebUI、trades.jsonl、风控和 5m 市场窗口。

建议用途：

- 复制/借鉴 `client.py`、`signer.py`、`websocket_client.py`、`gamma_client.py` 的结构。
- 不整包替换当前项目。

### 3. ddchack/sharkflow

地址：https://github.com/ddchack/sharkflow

可借鉴：

- 有 BTC 5m Rush Mode。
- 有 FastAPI 后端、Dashboard、风险管理、CLOB WebSocket、市场扫描、Kelly/EV 等模块。
- UI 思路和策略监控思路有参考价值。

不能直接拿来跑的原因：

- GitHub 星标少、无正式 release。
- README 仍写 `py-clob-client`，需确认是否完全 CLOB v2 / pUSD / deposit wallet 兼容。
- 体量很大，直接合并会引入大量我们不需要的 LLM、体育、鲸鱼跟踪、复杂数学模块。

建议用途：

- 借鉴 `rush_mode.py`、`risk_manager.py`、`ws_client.py`、`dashboard.html` 的思路。
- 不作为执行层可信来源。

### 4. 最终建议

不要找“一键成熟 bot”替换当前项目。正确路线：

1. 官方 SDK + relayer 完成 deposit wallet 下单闭环。
2. 从 discountry 项目借鉴 gasless/builder/relayer/WebSocket 代码组织。
3. 从 SharkFlow 借鉴 BTC 5m、风险管理和 dashboard 思路。
4. 保留我们已跑通的数据采集、WebUI 和策略配置。
5. 最终只替换执行器：`browser_magic` -> `backend_deposit_wallet`。
