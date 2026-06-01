# Codex 续接 WebUI 性能验收报告

时间：2026-06-01 14:40（Asia/Shanghai）

## 项目现状

- WebUI 地址：http://localhost:5175/
- 当前 WebUI 可以打开，5175 已重启为隐藏后台 Python 进程。
- 本轮没有点击“启动模拟”“启动实盘”，没有触发实盘交易，没有删除旧文件或数据。
- 阶段 6 严格回测结论仍然不变：严格样本不足，暂不建议切换模拟盘策略。

## 实际浏览器验证记录

已使用 Playwright/Chromium 真实打开并切换：

- 交易控制
- 市场数据
- 数据分析
- 用户中心
- 交易记录分页

验证结果：

- 控制台错误：0
- 请求失败：0
- 表头固定：交易记录 17 列均为 sticky；市场列表/分析/用户中心表格表头也已固定。
- 交易记录分页可用；本轮修正了验收脚本，避免误点策略槽位。

## 截图路径

目录：
`C:\Users\yyq\Desktop\自动交易\webui\截图\新WebUI\Codex验收\`

新增/覆盖截图：

- `23_续接验收_交易控制.png`
- `24_续接验收_市场数据.png`
- `25_续接验收_数据分析.png`
- `26_续接验收_用户中心.png`
- `27_续接验收_交易记录分页.png`
- `28_市场回放_缓存后.png`
- `29_市场回放_缓存二次.png`
- `30_市场回放_等待10秒.png`
- `codex_webui_audit_report.json`

## 完整问题清单

必须修复：

- 市场数据页首次进入仍然偏慢，原因是先请求 `market-windows`，再请求当前市场 `market-tick-data`。
- 当前官方 RTDS/Chainlink BTC 秒级价格断流或滞后，市场回放当前市场只有盘口概率曲线，没有 BTC 价格曲线。
- 用户中心显示“官方价格：服务异常/数据质量 degraded”，这不是纯 WebUI 展示问题，需要继续检查采集器。

建议优化：

- 市场回放加载时应明确显示“正在加载盘口/价格”，并在缺少官方 BTC tick 时提示“仅有盘口概率，BTC 价格缺失”，避免误以为图表坏了。
- `/api/safety` 当前约 2.7 秒，不适合高频刷新；目前它只在慢刷新里调用，后续可加 10-15 秒缓存。
- 市场数据页可以改成进入页面先显示列表，再异步加载回放图，不阻塞主页面体感。

可选新增：

- 在市场回放图上加“数据覆盖率”小标识：价格点数量、盘口点数量、是否可用于回测。
- 在数据分析页加“严格回测可用样本”卡片，区分完整市场和真正能做价差策略回测的市场。

## 假数据和未连接功能清单

本轮没有发现新增 Math.random 或明显假数据。

但当前仍有两个“容易误解”的真实问题：

- 市场回放的 BTC 价格不是假数据，而是当前采集文件没有该市场官方价格 tick，所以显示为空。
- 数据分析资金趋势之前加载慢，不是假数据，主要是后端做了不必要的 resolution 文件读取。

## 已完成修改

1. 增加后端轻量缓存：
   - `read_trades()` 增加 3 秒文件签名缓存。
   - `load_windows()` 增加 5 秒文件签名缓存。
   - `resolution_by_slug()` 增加 60 秒文件签名缓存。
2. 删除 `/api/fund-trend` 中重复且未使用的 `resolution_by_slug(5000)` 读取。
3. 新增 Playwright 验收脚本：
   - 真实打开页面。
   - 切换 4 个主页面。
   - 记录控制台错误、请求失败、接口耗时。
   - 截图保存到指定验收目录。
   - 明确跳过启动模拟/启动实盘。

## 修改文件

- `C:\Users\yyq\Desktop\自动交易\webui\api_server.py`
- `C:\Users\yyq\Desktop\自动交易\webui-check\codex_webui_audit.js`

## 前后端字段映射结果

本轮重点检查的链路：

- 顶部状态栏：`TopBar` → `/api/status` → `true_market_snapshot()`、采集器快照、Coinbase fallback 展示价。
- 交易记录：`TradeTable` → `/api/trades?p=1&ps=100` → `btc5m数据/trades.jsonl`。
- 市场列表：`MarketDataPage` → `/api/market-windows?limit=200` → `windows.jsonl`、`resolutions.jsonl`、交易记录。
- 市场回放：`MarketDataPage` → `/api/market-tick-data?slug=...` → `price_ticks.jsonl`、`orderbook_ticks.jsonl`。
- 数据分析：`AnalyticsPage` → `/api/fund-trend`、`/api/skip-reasons`、`/api/summary`。
- 用户中心：`UserCenterPage` → `/api/wallet`、`/api/data-quality`、`/api/safety`。

## 数据刷新与性能验证

优化前浏览器验收慢请求：

- `/api/fund-trend`：约 6960ms
- `/api/market-tick-data`：约 6330ms
- `/api/market-windows`：约 2508ms

优化后浏览器验收慢请求：

- `/api/fund-trend`：约 354ms
- `/api/market-tick-data`：约 1880ms
- `/api/market-windows`：约 1924ms

结论：

- 数据分析页卡顿已明显降低。
- 市场回放仍需要继续优化和改善加载提示。
- 当前官方价格采集异常会导致市场回放缺 BTC 曲线，这会影响回测样本增长。

## 旧文件待删除清单

本轮不删除旧 WebUI 文件。

可等新 WebUI 完全稳定后再列清单：

- 旧验收脚本
- 旧截图
- 旧 WebUI 入口或临时检查文件

## btc5m数据统计

沿用阶段 5/6 当前结论：

- 完整可回测市场：约 338-340 个，随采集增长变化。
- 但具备最后 120 秒官方 BTC tick 的严格样本仍偏少。
- 当前用户中心显示官方价格服务异常，说明新数据的严格回测可用性仍需继续观察。

## 回测结果

本轮没有重新选择策略。

阶段 6 结论保持：

- 不建议根据当前严格小样本切换模拟盘策略。
- 高概率买入的赔率结构很极端，输一笔会覆盖很多小盈利，必须用足够样本验证。

## 推荐策略

暂不推荐切换。

继续收集数据，优先确保：

- 最后 120 秒官方 BTC tick 覆盖。
- 盘口 Up/Down 双边快照覆盖。
- `$1 market buy` full fill 可重放。

## 模拟盘运行方案

暂不启动新的模拟策略。

后续进入阶段 7 前，需要你确认策略候选。确认后才切换模拟盘；每笔模拟下注金额按你的要求保持最低 1 美元。

## 需要你确认的事项

- 是否允许下一步继续修复采集器官方价格断流问题。
- 是否允许我把市场回放增加“价格缺失/仅盘口”提示，并把加载态做得更清楚。
- 是否保留 `webui-check/codex_webui_audit.js` 作为以后每轮 WebUI 验收脚本。

## 主动建议

下一步优先级建议：

1. 先修官方 BTC tick 采集异常，否则市场回放和严格回测都会继续缺样本。
2. 再优化市场数据页：先显示列表，回放图异步加载，缺数据时明确说明。
3. 再做视觉微调：策略槽位、交易记录列宽、数据分析页图表密度、用户中心状态说明。
