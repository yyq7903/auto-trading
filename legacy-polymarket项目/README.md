# Polymarket BTC 5M 自动交易系统

## 项目结构

```
polymarket项目/
├── btc5m-collector/     # 数据采集器
│   ├── collect.py       # 主程序（Chainlink + SSR + WebSocket）
│   └── collect.log      # 运行日志
├── btc5m-trader/        # 交易机器人
│   ├── trader.py        # 主程序（自动下单 + 复利管理）
│   ├── .env.example     # 配置模板（实盘需填私钥）
│   └── check_notify.py  # 通知检查脚本
├── btc5m-webui/         # 可视化面板
│   ├── index.html       # WebUI 主页（ECharts图表）
│   ├── echarts.min.js   # ECharts 本地库
│   ├── data.json        # 市场数据（自动生成）
│   ├── trader.json      # 交易机器人状态（自动生成）
│   ├── prepare.py       # 数据预处理脚本
│   └── trader_data.py   # WebUI数据生成器（长驻进程）
├── btc5m数据/           # 原始数据文件
│   ├── all_events.jsonl  # WebSocket事件
│   ├── btc_price.jsonl   # Chainlink BTC价格（每秒）
│   ├── markets.jsonl     # 市场元数据
│   ├── trades.jsonl      # 交易记录
│   └── trader_state.json # 账户状态
├── 启动采集器.bat       # Windows启动脚本
├── 启动交易机器人.bat
└── 启动WebUI.bat
```

## 策略参数

| 参数 | 值 | 说明 |
|------|------|------|
| 入场时间 | 最后5秒 | T-5s |
| 价差阈值 | ≥ $10 | BTC与PTB的绝对偏差 |
| 概率过滤 | ≥ 60% | 赢面方token概率 |
| 价格过滤 | 0.05~0.95 | 避免极端价格 |
| 下注比例 | 50% | 每次用总资金的50% |
| 提利规则 | 3x | 总资金达3倍时提利润 |

## 数据来源

1. **Polymarket CLOB WebSocket** — Token实时价格/订单簿
2. **Polymarket SSR** — PTB（Price to Beat）+ 历史结算
3. **Polymarket Gamma API** — 市场元数据（token ID）
4. **Chainlink RPC (Polygon)** — BTC实时价格（Polymarket结算源）

## 快速启动

### 方式1：systemd服务（推荐，后台运行）
```bash
# WSL中执行
systemctl --user start btc5m-collector
systemctl --user start btc5m-trader
systemctl --user start btc5m-trader-data
```

### 方式2：Windows批处理
双击对应的 .bat 文件即可。

### WebUI
浏览器打开 http://localhost:8877

## 切换实盘

1. 复制 `.env.example` 为 `.env`
2. 填入 `PRIVATE_KEY=你的私钥`
3. 改 `MODE=live`
4. 重启 trader 服务

## 当前状态

- 模式：模拟（sim）
- 回测：171个市场100%胜率（56/56满足条件）
- 瓶颈：73%市场最后10秒流动性差（token价0.99/0.01不可执行）
