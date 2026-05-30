import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  App as AntApp,
  Badge,
  Button,
  Card,
  Col,
  ConfigProvider,
  Descriptions,
  Divider,
  Form,
  Input,
  InputNumber,
  Layout,
  Progress,
  Row,
  Segmented,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  theme,
} from "antd";
import {
  BarChartOutlined,
  CheckCircleFilled,
  ControlOutlined,
  DatabaseOutlined,
  ExportOutlined,
  LineChartOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
  WalletOutlined,
} from "@ant-design/icons";
import * as echarts from "echarts";
import { api } from "./api";
import type {
  BackendEvent,
  DataQualityState,
  MarketDetail,
  MarketWindowRow,
  SafetyState,
  StatusState,
  Strategy,
  StrategyConfig,
  SummaryState,
  TradeRow,
  TradesResponse,
  WalletState,
} from "./types";
import "./styles.css";

const { Header, Content } = Layout;
const { Text } = Typography;

const money = (v?: number | string) => {
  if (v === null || v === undefined || v === "") return "--";
  const n = Number(v);
  if (isNaN(n) || n === 0) return "--";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 6 })}`;
};

const compactMoney = (v?: number | string | null) => {
  if (v === null || v === undefined || v === "") return "--";
  const n = Number(v);
  if (isNaN(n) || n === 0) return "--";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
};

const pct = (v?: number | string) => `${Number(v || 0).toFixed(1)}%`;
const price3 = (v?: number | string | boolean) => {
  if (v === null || v === undefined || v === "") return "--";
  const n = Number(v);
  if (isNaN(n) || n === 0) return "--";
  return n.toFixed(3);
};

const fmtTime = (value?: string) => {
  if (!value) return "--";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value.slice(5, 19);
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
};

const signedDollar = (v?: number | string | null) => {
  if (v === null || v === undefined || v === "") return <Text type="secondary">--</Text>;
  const n = Number(v);
  if (!Number.isFinite(n)) return <Text type="secondary">--</Text>;
  return <span className={n >= 0 ? "green strong" : "red strong"}>{n >= 0 ? "+" : ""}${Math.round(n).toLocaleString()}</span>;
};

const signedPct = (v?: number | string | null) => {
  if (v === null || v === undefined || v === "") return <Text type="secondary">--</Text>;
  const n = Number(v);
  if (!Number.isFinite(n)) return <Text type="secondary">--</Text>;
  return <span className={n >= 0 ? "green strong" : "red strong"}>{n >= 0 ? "+" : ""}{n.toFixed(1)}%</span>;
};

const btcPrice = (v?: number | string | null, className = "") => {
  if (v === null || v === undefined || v === "") return <Text type="secondary">--</Text>;
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return <Text type="secondary">--</Text>;
  return <span className={className}>${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>;
};

const marketProbability = (v?: number | string | null) => {
  if (v === null || v === undefined || v === "") return <Text type="secondary">--</Text>;
  const n = Number(v);
  if (!Number.isFinite(n) || n <= 0) return <Text type="secondary">--</Text>;
  const price = n > 1 && n <= 100 ? n / 100 : n;
  return `$${price.toFixed(3)}`;
};

const fmtMarketWindow = (start?: number | string, end?: number | string) => {
  const s = Number(start || 0);
  const e = Number(end || 0);
  if (!s || !e) return "--";
  const sd = new Date(s * 1000);
  const ed = new Date(e * 1000);
  const date = `${sd.getFullYear()}/${sd.getMonth() + 1}/${sd.getDate()}`;
  const st = `${String(sd.getHours()).padStart(2, "0")}:${String(sd.getMinutes()).padStart(2, "0")}`;
  const et = `${String(ed.getHours()).padStart(2, "0")}:${String(ed.getMinutes()).padStart(2, "0")}`;
  return `${date} ${st}-${et}`;
};

function useChart(id: string, option: echarts.EChartsOption, deps: React.DependencyList) {
  useEffect(() => {
    const el = document.getElementById(id);
    if (!el) return;
    const chart = echarts.init(el, "dark");
    chart.setOption(option);
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, deps);
}

function AppShell() {
  const [safety, setSafety] = useState<SafetyState | null>(null);
  const [status, setStatus] = useState<StatusState | null>(null);
  const [summary, setSummary] = useState<SummaryState | null>(null);
  const [strategies, setStrategies] = useState<StrategyConfig | null>(null);
  const [wallet, setWallet] = useState<WalletState | null>(null);
  const [dataQuality, setDataQuality] = useState<DataQualityState | null>(null);
  const [trades, setTrades] = useState<TradesResponse>({ trades: [], total: 0, page: 1, pages: 1, per_page: 20 });
  const [activeTab, setActiveTab] = useState("trade");
  const [fundTrend, setFundTrend] = useState<{data: Array<{time: string, bankroll: number, pnl: number, slug: string}>, initial: number}>({data: [], initial: 100});
  const [skipReasons, setSkipReasons] = useState<{data: Array<{name: string, value: number}>, total: 0}>({data: [], total: 0});
  const [tradePage, setTradePage] = useState(1);
  const [mode, setMode] = useState<"sim" | "live">("sim");
  const [notifications, setNotifications] = useState<Array<{id: number, type: 'info' | 'warning' | 'error' | 'success', message: string, time: string}>>([]);

  // 閫氱煡鍑芥暟
  const addNotification = useCallback((type: 'info' | 'warning' | 'error' | 'success', message: string) => {
    const id = Date.now();
    const time = new Date().toLocaleTimeString();
    setNotifications(prev => [...prev.slice(-9), {id, type, message, time}]);
    // 5绉掑悗鑷姩娑堝け
    setTimeout(() => {
      setNotifications(prev => prev.filter(n => n.id !== id));
    }, 5000);
  }, []);

  const alertOnce = useCallback((key: string, type: 'info' | 'warning' | 'error' | 'success', message: string, cooldownMs = 30000) => {
    const now = Date.now();
    const store = ((window as any).__alertTimes ||= {});
    if (!store[key] || now - store[key] > cooldownMs) {
      store[key] = now;
      addNotification(type, message);
    }
  }, [addNotification]);

  const refreshFast = useCallback(async () => {
    const [stat, rows] = await Promise.all([
      api.status(),
      api.trades(tradePage, 20),
    ]);
    setStatus(stat);
    setTrades(rows);
    
    const currentSlug = stat?.current_market?.slug || "";
    const lastSlug = (window as any).__lastSlug || "";
    if (currentSlug && currentSlug !== lastSlug) {
      addNotification("info", `市场切换: ${currentSlug}`);
      (window as any).__lastSlug = currentSlug;
    }
  }, [tradePage, addNotification]);

  const refreshQuality = useCallback(async () => {
    const quality = await api.dataQuality();
    setDataQuality(quality);

    if (quality?.current_window_quality === "stale") {
      alertOnce("quality-stale", "warning", "数据质量: 窗口已过期");
    }
    if (!quality?.clob_ws_online) {
      alertOnce("clob-offline", "error", "盘口离线");
    }
    if (!quality?.rtds_chainlink_online) {
      alertOnce("rtds-offline", "warning", "官方价格离线");
    }
  }, [alertOnce]);

  const refreshSlow = useCallback(async () => {
    const [safe, sum, strat, walletState, trend, reasons] = await Promise.all([
      api.safety(),
      api.summary(),
      api.strategies(),
      api.wallet(),
      api.fundTrend().catch(() => ({data: [], initial: 100})),
      api.skipReasons().catch(() => ({data: [], total: 0})),
    ]);
    setSafety(safe);
    setSummary(sum);
    setStrategies(strat);
    setWallet(walletState);
    setFundTrend(trend);
    setSkipReasons(reasons);
  }, []);

  const refresh = useCallback(async () => {
    await Promise.all([refreshFast(), refreshQuality(), refreshSlow()]);
  }, [refreshFast, refreshQuality, refreshSlow]);

  const [countdown, setCountdown] = useState(0);
  const [serverTimeOffset, setServerTimeOffset] = useState(0);

  const ticker = status?.ticker || {};
  const market = status?.current_market || {};
  const displaySecondsLeft = countdown > 0 ? countdown : Number(market.seconds_left || 0);
  const marketStale = dataQuality?.current_window_quality === "stale" || Number(dataQuality?.remaining_seconds || 0) < -5;

  useEffect(() => {
    refresh().catch(console.error);
    const fastId = window.setInterval(() => refreshFast().catch(console.error), 1000);
    const qualityId = window.setInterval(() => refreshQuality().catch(console.error), 5000);
    const slowId = window.setInterval(() => refreshSlow().catch(console.error), 15000);
    return () => {
      window.clearInterval(fastId);
      window.clearInterval(qualityId);
      window.clearInterval(slowId);
    };
  }, [refresh, refreshFast, refreshQuality, refreshSlow]);

  // 本地倒计时：每秒递减
  useEffect(() => {
    const sl = Number(market.seconds_left || 0);
    setCountdown(sl);
  }, [market.seconds_left]);

  useEffect(() => {
    const tick = window.setInterval(() => {
      setCountdown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => window.clearInterval(tick);
  }, []);

  return (
    <ConfigProvider
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: "#2f8cff",
          colorSuccess: "#2ac769",
          colorError: "#ff4d4f",
          colorWarning: "#f6b73c",
          borderRadius: 6,
          fontFamily: "Inter, Segoe UI, Arial, sans-serif",
        },
      }}
    >
      <AntApp>
        <Layout className="app-layout">
          <Header className="topbar">
            <div className="brand">
              <BarChartOutlined />
              <span>BTC 5M</span>
              <Text type="secondary">{summary?.total || 0} 记录 | 最近100条循环显示</Text>
            </div>
            <div className="ticker">
              <Badge status={safety?.route_ready ? "success" : "warning"} />
              {marketStale ? <Tag color="warning">市场切换中</Tag> : null}
              <span>剩余 <b style={{ color: displaySecondsLeft <= 15 ? '#ff4d4f' : displaySecondsLeft <= 30 ? '#f6b73c' : '#2ac769' }}>{displaySecondsLeft}</b>s</span>
              <span>{fmtMarketWindow(market.window_start_ts, market.window_end_ts)}</span>
              <span>现价 <b>{compactMoney(ticker.chainlink_price || ticker.btc_price)}</b></span>
              <span>开盘价 <b>{compactMoney(ticker.open_price || ticker.ptb)}</b></span>
              <span className={Number(ticker.gap || 0) >= 0 ? "green" : "red"}>价差 {compactMoney(ticker.gap)}</span>
              <span>Up {Number(ticker.up_price || 0).toFixed(3)}</span>
              <span>Down {Number(ticker.down_price || 0).toFixed(3)}</span>
              <span>实盘余额 <b>{money(wallet?.clob_balance)}</b></span>
            </div>
            <Button icon={<ReloadOutlined />} onClick={() => refresh().catch(console.error)}>
              刷新
            </Button>
          </Header>
          <Content className="content">
            <Tabs
              activeKey={activeTab}
              onChange={setActiveTab}
              items={[
                {
                  key: "trade",
                  label: (
                    <span>
                      <ControlOutlined /> 交易控制
                    </span>
                  ),
                  children: (
                    <TradeControl
                      mode={mode}
                      setMode={setMode}
                      safety={safety}
                      status={status}
                      strategies={strategies}
                      wallet={wallet}
                      dataQuality={dataQuality}
                      onRefresh={refresh}
                    />
                  ),
                },
                {
                  key: "market-data",
                  label: <span><DatabaseOutlined /> 市场数据</span>,
                  children: <MarketDataView />,
                },
                {
                  key: "user",
                  label: (
                    <span>
                      <UserOutlined /> 用户中心
                    </span>
                  ),
                  children: (
                    <UserCenter safety={safety} status={status} wallet={wallet} dataQuality={dataQuality} onRefresh={refresh}>
                      <DailySummaryView summary={summary} />
                    </UserCenter>
                  ),
                },
              ]}
            />
            <RecentTrades trades={trades} page={tradePage} setPage={setTradePage} />
          </Content>
        </Layout>
      </AntApp>
    </ConfigProvider>
  );
}

function TradeControl({
  mode,
  setMode,
  safety,
  status,
  strategies,
  wallet,
  dataQuality,
  onRefresh,
  children,
}: {
  mode: "sim" | "live";
  setMode: (mode: "sim" | "live") => void;
  safety: SafetyState | null;
  status: StatusState | null;
  strategies: StrategyConfig | null;
  wallet: WalletState | null;
  dataQuality: DataQualityState | null;
  onRefresh: () => Promise<void>;
  children?: React.ReactNode;
}) {
  const { message } = AntApp.useApp();
  const activeId = strategies?.active_strategy || "1";
  const active = strategies?.strategies?.[activeId];
  const [editing, setEditing] = useState<{ id: string; item: Strategy } | null>(null);
  const [switchingSlot, setSwitchingSlot] = useState<string | null>(null);
  const [controlBusy, setControlBusy] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    if (active) {
      setEditing({ id: activeId, item: active });
      form.setFieldsValue({ name: active.name, ...active.params });
    }
  }, [activeId, active, form]);

  const save = async () => {
    const values = await form.validateFields();
    await api.updateStrategy(editing?.id || activeId, values.name, {
      entry_second: values.entry_second,
      gap_threshold: values.gap_threshold,
      min_buy_price: values.min_buy_price,
      bet_fraction: values.bet_fraction,
      cooldown_seconds: values.cooldown_seconds,
    });
    message.success("策略参数已保存到当前槽位");
    await onRefresh();
  };

  const restore = () => {
    if (!active) return;
    form.setFieldsValue({ name: active.name, ...active.params });
    message.info("已恢复当前槽位参数");
  };

  const switchSlot = async (id: string) => {
    setSwitchingSlot(id);
    try {
      await api.switchStrategy(id);
      message.success(`已切换到策略 ${id}`);
      await onRefresh();
    } finally {
      setSwitchingSlot(null);
    }
  };

  const toggleRun = async () => {
    const action = running ? "pause" : "start";
    setControlBusy(true);
    try {
      await api.toggle(action, mode);
      if (mode === "sim") {
        message.success(action === "start" ? "模拟交易已启动" : "模拟交易已暂停");
      } else {
        message.success(action === "start" ? "实盘启动请求已提交" : "实盘已暂停");
      }
    } catch (error) {
      message.warning(error instanceof Error ? error.message : "操作失败");
    } finally {
      setControlBusy(false);
    }
    await onRefresh();
  };

  const running = mode === "sim" ? safety?.sim_trading : safety?.ready_to_trade;
  const controlLabel = `${running ? "暂停" : "启动"}${mode === "sim" ? "模拟" : "实盘"}`;

  // 计算跳过原因统计
  const skipReasons = useMemo(() => {
    // 后续可以从 trades 数据里补充统计。
    return {};
  }, []);

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={15}>
        <Card className="panel" title="策略槽位">
          <Space wrap className="slot-grid">
            {Object.entries(strategies?.strategies || {}).slice(0, 5).map(([id, item]) => (
              <button
                className={`slot ${id === activeId ? "active" : ""} ${switchingSlot === id ? "switching" : ""}`}
                key={id}
                disabled={!!switchingSlot}
                onClick={() => switchSlot(id)}
              >
                <span>策略 {id}</span>
                <b>{item.name}</b>
                <small>{switchingSlot === id ? "策略切换中" : `回测 ${pct(item.win_rate || 0)}`}</small>
              </button>
            ))}
          </Space>
          <Divider />
          <div className="strategy-overview" style={{ marginBottom: 16 }}>
            <Row gutter={[16, 8]}>
              <Col span={6}>
                <Statistic title="监控窗口" value={`T-${active?.params?.entry_second || 25}s 内`} />
              </Col>
              <Col span={6}>
                <Statistic title="价差阈值" value={`$${active?.params?.gap_threshold || 10}`} />
              </Col>
              <Col span={6}>
                <Statistic title="最低概率" value={`${((active?.params?.min_buy_price || 0.6) * 100).toFixed(0)}%`} />
              </Col>
              <Col span={6}>
                <Statistic title="仓位比例" value={`${((active?.params?.bet_fraction || 1) * 100).toFixed(0)}%`} />
              </Col>
            </Row>
          </div>
          <Form form={form} layout="vertical" className="param-form">
            <Row gutter={12}>
              <Col xs={24} md={8}>
                <Form.Item label="槽位名称" name="name" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
              </Col>
              <Param name="entry_second" label="入场窗口秒数 (1-120)" min={1} max={120} />
              <Param name="gap_threshold" label="价差阈值 (0-500)" min={0} max={500} />
              <Param name="min_buy_price" label="最低概率 (0.01-0.99)" min={0.01} max={0.99} step={0.01} />
              <Param name="bet_fraction" label="仓位比例 (0.01-1.0)" min={0.01} max={1} step={0.01} />
              <Param name="cooldown_seconds" label="冷却秒数 (0-3600)" min={0} max={3600} />
            </Row>
            <Space wrap>
              <Button type="primary" icon={<DatabaseOutlined />} onClick={save}>
                保存到当前槽位
              </Button>
              <Button onClick={restore}>恢复当前槽位</Button>
            </Space>
          </Form>
        </Card>
        <MarketSnapshot status={status} dataQuality={dataQuality} />
      </Col>
      <Col xs={24} xl={9}>
        <Card className="panel" title="交易控制">
          <Segmented
            block
            value={mode}
            onChange={(value) => setMode(value as "sim" | "live")}
            options={[
              { value: "sim", label: "模拟交易" },
              { value: "live", label: "实盘交易" },
            ]}
          />
          <div className="mode-card">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="模拟服务">
                <Health ok={!!safety?.sim_active} text={safety?.sim_active ? "已连接" : "未连接"} />
              </Descriptions.Item>
              <Descriptions.Item label="实盘连接">
                <Health ok={!!safety?.live_connected} text={safety?.live_connected ? "已接通，可以下单" : "未接通"} />
              </Descriptions.Item>
              <Descriptions.Item label="运行状态">
                <Tag color={running ? "success" : "default"}>{running ? "运行中" : "已暂停"}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="当前模式">
                <Tag color={mode === "sim" ? "blue" : "orange"}>{mode === "sim" ? "模拟" : "实盘"}</Tag>
              </Descriptions.Item>
            </Descriptions>
            <Space className="control-buttons" wrap>
              <Button
                type={running ? "default" : "primary"}
                danger={!!running}
                loading={controlBusy}
                icon={running ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                onClick={toggleRun}
              >
                {controlLabel}
              </Button>
            </Space>
            <Text type="secondary">
              {mode === "live"
                ? "实盘小额下单已验证；自动循环接好前，系统会拦截异常启动。"
                : running
                  ? "模拟交易运行中"
                  : "模拟交易已暂停"}
            </Text>
          </div>
          <Divider />
          <DataQualityCard dataQuality={dataQuality} compact />
          <Divider />
          <RouteWalletSummary wallet={wallet} status={status} onRefresh={onRefresh} />
        </Card>
      </Col>
    </Row>
  );
}

function MarketSnapshot({ status, dataQuality }: { status: StatusState | null; dataQuality: DataQualityState | null }) {
  const ticker = status?.ticker || {};
  const market = status?.current_market || {};
  const open = Number(ticker.open_price || ticker.ptb || 0);
  const current = Number(ticker.chainlink_price || ticker.btc_price || 0);
  const gap = Number(ticker.gap || 0);
  const quality = String(market.ptb_quality || ticker.ptb_quality || dataQuality?.current_window_quality || "missing");
  const qualityColor = quality === "exact" || quality === "good" ? "success" : quality === "close" || quality === "degraded" ? "warning" : "error";
  const secondsLeft = Number(market.seconds_left || 0);
  const usable = secondsLeft > 0 && dataQuality?.current_window_quality !== "stale" && !market.exclude_from_backtest;

  return (
    <Card className="panel market-card" title="当前市场观察">
      <Row gutter={[12, 12]}>
        <Col xs={24} md={10}>
          <Descriptions column={1} size="small">
            <Descriptions.Item label="市场时间">{fmtMarketWindow(market.window_start_ts, market.window_end_ts)}</Descriptions.Item>
            <Descriptions.Item label="市场编号">{market.slug || "--"}</Descriptions.Item>
            <Descriptions.Item label="价格来源">{String(ticker.source || "--")}</Descriptions.Item>
            <Descriptions.Item label="开盘价质量">
              <Tag color={qualityColor}>{quality || "--"}</Tag>
              {Number(market.ptb_diff || 0) ? <Text type="secondary"> 差值 {compactMoney(market.ptb_diff as number)}</Text> : null}
            </Descriptions.Item>
          </Descriptions>
        </Col>
        <Col xs={12} md={4}>
          <Statistic title="现价" value={current} precision={2} prefix="$" />
        </Col>
        <Col xs={12} md={4}>
          <Statistic title="开盘价" value={open} precision={2} prefix="$" />
        </Col>
        <Col xs={12} md={3}>
          <Statistic title="Up" value={Number(ticker.up_price || 0)} precision={3} />
          <Text type="secondary">买 {price3(ticker.up_ask)} / 卖 {price3(ticker.up_bid)}</Text>
        </Col>
        <Col xs={12} md={3}>
          <Statistic title="Down" value={Number(ticker.down_price || 0)} precision={3} />
          <Text type="secondary">买 {price3(ticker.down_ask)} / 卖 {price3(ticker.down_bid)}</Text>
        </Col>
      </Row>
      <div className="market-footer">
        <Tag color={gap >= 0 ? "success" : "error"}>价差 {gap >= 0 ? "+" : ""}{compactMoney(gap)}</Tag>
        <Tag color={dataQuality?.collector_running ? "success" : "error"}>采集器{dataQuality?.collector_running ? "运行中" : "未运行"}</Tag>
        <Tag color={dataQuality?.clob_ws_online ? "success" : "error"}>盘口{dataQuality?.clob_ws_online ? "在线" : "离线"}</Tag>
        <Tag color={dataQuality?.rtds_degraded ? "warning" : dataQuality?.rtds_chainlink_online ? "success" : "error"}>
          官方价格{dataQuality?.rtds_degraded ? "降级" : dataQuality?.rtds_chainlink_online ? "在线" : "离线"}
        </Tag>
        {usable ? <Tag color="success">可用于观察</Tag> : <Tag color="error">窗口已结束或数据异常</Tag>}
      </div>
    </Card>
  );
}

function RouteWalletSummary({
  wallet,
  status,
  onRefresh,
}: {
  wallet: WalletState | null;
  status: StatusState | null;
  onRefresh: () => Promise<void>;
}) {
  const { message } = AntApp.useApp();
  const simStats = status?.stats?.sim;
  const liveStats = status?.stats?.live;
  const totalStats = status?.stats?.total;
  const [simFunds, setSimFunds] = useState<number>(simStats?.bankroll || status?.trader_state.bankroll || 0);
  const [savingFunds, setSavingFunds] = useState(false);

  useEffect(() => {
    setSimFunds(simStats?.bankroll || status?.trader_state.bankroll || 0);
  }, [simStats?.bankroll, status?.trader_state.bankroll]);

  const saveSimFunds = async () => {
    setSavingFunds(true);
    try {
      await api.setSimFunds(Number(simFunds || 0));
      message.success("模拟资金已更新");
      await onRefresh();
    } catch (error) {
      message.warning(error instanceof Error ? error.message : "模拟资金更新失败");
    } finally {
      setSavingFunds(false);
    }
  };

  return (
    <>
      <Row gutter={[12, 12]}>
        <Col xs={12} md={8}>
          <Statistic title="实盘余额" value={wallet?.clob_balance || 0} precision={6} prefix="$" />
        </Col>
        <Col xs={12} md={8}>
          <Statistic title="模拟资金" value={simStats?.bankroll ?? status?.trader_state.bankroll ?? 0} precision={2} prefix="$" />
        </Col>
        <Col xs={12} md={8}>
          <Statistic title="模拟胜率" value={simStats?.win_rate ?? calcWinRate(status)} suffix="%" precision={1} />
        </Col>
        <Col xs={12} md={8}>
          <Statistic title="实盘胜率" value={liveStats?.win_rate ?? 0} suffix="%" precision={1} />
        </Col>
        <Col xs={12} md={8}>
          <Statistic title="总胜率" value={totalStats?.win_rate ?? calcWinRate(status)} suffix="%" precision={1} />
        </Col>
      </Row>
      <Space.Compact className="sim-funds-control">
        <InputNumber
          min={1}
          max={1000000}
          precision={2}
          value={simFunds}
          addonBefore="模拟资金 $"
          onChange={(value) => setSimFunds(Number(value || 0))}
        />
        <Button loading={savingFunds} onClick={saveSimFunds}>保存</Button>
      </Space.Compact>
      <div className="wallet-strip">
        <Tag color={wallet?.wallet_deployed ? "success" : "warning"}>实盘钱包{wallet?.wallet_deployed ? "正常" : "未确认"}</Tag>
        <Tag color={wallet?.allowance_ready ? "success" : "warning"}>扣款授权{wallet?.allowance_ready ? "已完成" : "待授权"}</Tag>
        <Tag color={wallet?.clob_ok ? "success" : "error"}>交易接口{wallet?.clob_ok ? "正常" : "异常"}</Tag>
      </div>
      {wallet?.deposit_wallet_url ? (
        <Button className="wide-link" href={wallet.deposit_wallet_url} target="_blank" icon={<ExportOutlined />}>
          打开实盘钱包
        </Button>
      ) : null}
    </>
  );
}

function DataQualityCard({ dataQuality, compact = false }: { dataQuality: DataQualityState | null; compact?: boolean }) {
  const quality = dataQuality?.current_window_quality || "missing";
  const color = quality === "good" ? "success" : quality === "degraded" ? "warning" : "error";
  const stats = dataQuality?.stats || {};
  const lines = dataQuality?.line_counts || {};
  const statusAge = dataQuality?.status_age_ms ?? 0;

  return (
    <div className={compact ? "quality-compact" : ""}>
      <Space wrap className="wallet-strip">
        <Tag color={color}>数据质量：{quality === "good" ? "良好" : quality === "degraded" ? "可用但需观察" : "异常"}</Tag>
        <Tag color={dataQuality?.collector_running ? "success" : "error"}>采集器{dataQuality?.collector_running ? "运行中" : "未运行"}</Tag>
        <Tag color={dataQuality?.clob_ws_online ? "success" : "error"}>盘口{dataQuality?.clob_ws_online ? "在线" : "离线"}</Tag>
        <Tag color={dataQuality?.rtds_degraded ? "warning" : dataQuality?.rtds_chainlink_online ? "success" : "error"}>
          官方价格{dataQuality?.rtds_degraded ? "降级" : dataQuality?.rtds_chainlink_online ? "在线" : "离线"}
        </Tag>
      </Space>
      <Descriptions column={compact ? 1 : 2} size="small">
        <Descriptions.Item label="当前市场">{dataQuality?.current_market_slug || "--"}</Descriptions.Item>
        <Descriptions.Item label="剩余秒数">{dataQuality?.remaining_seconds ?? "--"}</Descriptions.Item>
        <Descriptions.Item label="窗口盘口数">{dataQuality?.current_window_tick_count ?? 0}</Descriptions.Item>
        <Descriptions.Item label="最新价格">{compactMoney(dataQuality?.price_last_value || 0)}</Descriptions.Item>
        <Descriptions.Item label="状态延迟">{statusAge ? `${Math.round(statusAge / 1000)}s` : "实时"}</Descriptions.Item>
        <Descriptions.Item label="价格来源">{dataQuality?.price_last_source || "--"}</Descriptions.Item>
      </Descriptions>
      {!compact ? (
        <Row gutter={12} className="quality-stats">
          <Col xs={12} md={4}><Statistic title="价格tick" value={stats.price_ticks ?? lines.price_ticks ?? 0} /></Col>
          <Col xs={12} md={4}><Statistic title="盘口tick" value={stats.orderbook_ticks ?? lines.orderbook_ticks ?? 0} /></Col>
          <Col xs={12} md={4}><Statistic title="成交tick" value={stats.trade_ticks ?? lines.trade_ticks ?? 0} /></Col>
          <Col xs={12} md={4}><Statistic title="市场元数据" value={stats.market_meta ?? lines.market_meta ?? 0} /></Col>
          <Col xs={12} md={4}><Statistic title="结算记录" value={stats.resolutions ?? lines.resolutions ?? 0} /></Col>
          <Col xs={12} md={4}><Statistic title="窗口数" value={stats.windows ?? 0} /></Col>
        </Row>
      ) : null}
    </div>
  );
}

function Param({ name, label, min, max, step = 1 }: { name: string; label: string; min: number; max: number; step?: number }) {
  return (
    <Col xs={12} md={8}>
      <Form.Item label={label} name={name} rules={[{ required: true }]}>
        <InputNumber min={min} max={max} step={step} style={{ width: "100%" }} />
      </Form.Item>
    </Col>
  );
}

function MarketDataView() {
  const [markets, setMarkets] = useState<MarketWindowRow[]>([]);
  const [selectedSlug, setSelectedSlug] = useState("");
  const [detail, setDetail] = useState<MarketDetail | null>(null);
  const [loading, setLoading] = useState(false);

  const loadMarkets = useCallback(async () => {
    const res = await api.marketWindows();
    setMarkets(res.markets || []);
    if (!selectedSlug && res.markets?.[0]?.slug) {
      setSelectedSlug(res.markets[0].slug);
    }
  }, [selectedSlug]);

  useEffect(() => {
    loadMarkets().catch(console.error);
  }, [loadMarkets]);

  useEffect(() => {
    if (!selectedSlug) return;
    setLoading(true);
    api.marketDetail(selectedSlug)
      .then(setDetail)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [selectedSlug]);

  useEffect(() => {
    if (!detail) return;
    const el = document.getElementById("marketReplayChart");
    if (!el) return;
    const chart = echarts.init(el);
    const open = Number(detail.window.open_price || 0);
    const start = Number(detail.window.window_start_ts || 0) * 1000;
    const end = Number(detail.window.window_end_ts || 0) * 1000;
    const priceData = detail.prices.map((p) => [p.ts, p.price]);
    const gapData = detail.prices.map((p) => [p.ts, p.gap]);
    const upData = detail.orderbook.map((p) => [p.ts, p.up_prob]);
    const downData = detail.orderbook.map((p) => [p.ts, p.down_prob]);
    const entryMarks = (detail.trades || [])
      .filter((t) => t.entry_time || t.time)
      .map((t) => {
        const ts = typeof t.entry_time === "number" ? t.entry_time * 1000 : new Date(t.entry_time || t.time).getTime();
        const prob = Number(t.buy_prob || 0);
        return { xAxis: ts, name: `${t.direction || ""} ${prob ? `$${prob.toFixed(3)}` : ""}` };
      })
      .filter((m) => Number.isFinite(m.xAxis));

    chart.setOption({
      backgroundColor: "transparent",
      animation: false,
      color: ["#ff9b54", "#2f8cff", "#2ac769", "#ff4d4f", "#9aa7b7"],
      legend: { textStyle: { color: "#9aa7b7" }, top: 0 },
      grid: { left: 58, right: 58, top: 48, bottom: 64 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        valueFormatter: (v: unknown) => (typeof v === "number" ? v.toFixed(4) : String(v ?? "--")),
      },
      dataZoom: [
        { type: "inside", xAxisIndex: [0] },
        { type: "slider", xAxisIndex: [0], bottom: 18, height: 22 },
      ],
      xAxis: { type: "time", axisLabel: { color: "#8797aa" }, splitLine: { lineStyle: { color: "#1f2b38" } } },
      yAxis: [
        { type: "value", name: "BTC", scale: true, axisLabel: { color: "#8797aa" }, splitLine: { lineStyle: { color: "#1f2b38" } } },
        { type: "value", name: "概率", min: 0, max: 1, axisLabel: { color: "#8797aa", formatter: "{value}" }, splitLine: { show: false } },
        { type: "value", name: "价差", scale: true, show: false },
      ],
      series: [
        { name: "BTC价格", type: "line", yAxisIndex: 0, showSymbol: false, data: priceData },
        { name: "开盘线", type: "line", yAxisIndex: 0, showSymbol: false, data: open && start && end ? [[start, open], [end, open]] : [], lineStyle: { type: "dashed" } },
        { name: "Up买入概率", type: "line", yAxisIndex: 1, showSymbol: false, data: upData },
        { name: "Down买入概率", type: "line", yAxisIndex: 1, showSymbol: false, data: downData },
        {
          name: "价差",
          type: "line",
          yAxisIndex: 2,
          showSymbol: false,
          data: gapData,
          lineStyle: { width: 1, type: "dotted" },
          markLine: { silent: true, symbol: "none", data: [{ yAxis: 0, name: "开盘价差" }], lineStyle: { color: "#6b7788", type: "dashed" } },
          markPoint: { symbol: "pin", symbolSize: 44, data: entryMarks },
        },
      ],
    });
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [detail]);

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={7}>
        <Card className="panel market-list-card" title="市场列表" extra={<Button size="small" icon={<ReloadOutlined />} onClick={loadMarkets}>刷新</Button>}>
          <Table<MarketWindowRow>
            rowKey="slug"
            size="small"
            loading={!markets.length}
            dataSource={markets}
            pagination={{ pageSize: 12, showSizeChanger: false }}
            rowClassName={(r) => (r.slug === selectedSlug ? "selected-market-row" : "")}
            onRow={(record) => ({ onClick: () => setSelectedSlug(record.slug) })}
            columns={[
              { title: "时间", dataIndex: "market_time", width: 118 },
              { title: "结果", dataIndex: "winner", width: 72, render: (v) => v ? renderDirection(String(v)) : <Text type="secondary">--</Text> },
              { title: "价差", dataIndex: "final_gap", width: 76, render: signedDollar },
              { title: "标记", width: 86, render: (_, r) => (
                <Space size={4}>
                  {r.reversal ? <Tag color="warning">反转</Tag> : null}
                  {r.has_trade ? <Tag color={r.trade_status === "lost" ? "error" : "success"}>交易</Tag> : null}
                </Space>
              ) },
            ]}
          />
        </Card>
      </Col>
      <Col xs={24} xl={17}>
        <Card className="panel" title="市场回放" loading={loading}>
          <Row gutter={[12, 12]} className="market-stats-row">
            <Col xs={12} md={6}><Statistic title="开盘价" value={detail?.window.open_price || 0} precision={2} prefix="$" /></Col>
            <Col xs={12} md={6}><Statistic title="结算价" value={detail?.window.final_price || 0} precision={2} prefix="$" /></Col>
            <Col xs={12} md={6}><Statistic title="结算差" value={detail?.summary.final_gap || 0} precision={2} prefix="$" valueStyle={{ color: Number(detail?.summary.final_gap || 0) >= 0 ? "#2ac769" : "#ff4d4f" }} /></Col>
            <Col xs={12} md={6}><Statistic title="数据点" value={(detail?.summary.price_points || 0) + (detail?.summary.orderbook_points || 0)} /></Col>
          </Row>
          <Space wrap className="wallet-strip">
            <Tag color={detail?.summary.reversal ? "warning" : "default"}>{detail?.summary.reversal ? "出现反转" : "未检测到反转"}</Tag>
            <Tag color="blue">价格点 {detail?.summary.price_points || 0}</Tag>
            <Tag color="purple">盘口点 {detail?.summary.orderbook_points || 0}</Tag>
            <Tag color={detail?.window.winner === "Up" ? "success" : "error"}>结算 {detail?.window.winner || "--"}</Tag>
          </Space>
          <div id="marketReplayChart" className="market-replay-chart" />
        </Card>
      </Col>
    </Row>
  );
}

function DailySummaryView({ summary }: { summary: SummaryState | null }) {
  const rows = useMemo(() => [...(summary?.daily_summary || [])].reverse(), [summary]);
  useChart(
    "pnlChart",
    {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: rows.map((r) => r.date) },
      yAxis: { type: "value" },
      series: [
        {
          type: "bar",
          name: "每日盈亏",
          data: rows.map((r) => r.pnl),
          itemStyle: {
            color: (p: any) => (Number(p.value) >= 0 ? "#2ac769" : "#ff4d4f"),
          },
        },
      ],
    },
    [rows],
  );
  useChart(
    "volumeChart",
    {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: rows.map((r) => r.date) },
      yAxis: { type: "value" },
      series: [{ type: "line", smooth: true, name: "日交易量", data: rows.map((r) => r.volume), areaStyle: {} }],
    },
    [rows],
  );
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={12}>
        <Card className="panel" title="每日盈亏柱状图">
          <div id="pnlChart" className="chart" />
        </Card>
      </Col>
      <Col xs={24} xl={12}>
        <Card className="panel" title="日交易量图">
          <div id="volumeChart" className="chart" />
        </Card>
      </Col>
      <Col span={24}>
        <Card className="panel" title="每日明细表">
          <Table
            rowKey="date"
            size="small"
            dataSource={summary?.daily_summary || []}
            pagination={{ pageSize: 10 }}
            columns={[
              { title: "日期", dataIndex: "date" },
              { title: "交易量", dataIndex: "trades" },
              { title: "投入", dataIndex: "volume", render: compactMoney },
              { title: "盈利", dataIndex: "pnl", render: signedMoney },
              { title: "赢", dataIndex: "wins" },
              { title: "输", dataIndex: "losses" },
              { title: "跳过", dataIndex: "skipped" },
            ]}
          />
        </Card>
      </Col>
    </Row>
  );
}

function RecentTrades({ trades, page, setPage }: { trades: TradesResponse; page: number; setPage: (page: number) => void }) {
  const renderSettlement = (_: unknown, row: TradeRow) => {
    if (row.settlement_status === "pending") return <Tag color="processing">待平台结算</Tag>;
    if (row.settlement_status === "fallback_missing") return <Tag color="warning">平台结算价缺失</Tag>;
    return compactMoney(row.btc_final);
  };
  const renderTradeNote = (_: unknown, row: TradeRow) => {
    if (row.skip_reason) return row.skip_reason;
    if (row.settlement_status === "pending") return "等待平台 closePrice";
    if (row.settlement_status === "fallback_missing") return "未拿到平台结算价";
    return row.settle_source || "--";
  };
  const renderSettledMoney = (value: number | string | null, row: TradeRow) => {
    if (row.settlement_status === "pending") return <Typography.Text type="secondary">--</Typography.Text>;
    return signedMoney(value);
  };
  const renderSettledPct = (value: number | string | null, row: TradeRow) => {
    if (row.settlement_status === "pending") return <Typography.Text type="secondary">--</Typography.Text>;
    return signedPct(value);
  };
  const renderEntryTime = (value: number | null) => {
    if (value !== null && value !== undefined) return <span className={Number(value) <= 5 ? "red strong" : ""}>T-{value}s</span>;
    return <Text type="secondary">--</Text>;
  };
  const renderMarketId = (_: unknown, row: TradeRow) => {
    const id = row.window_start_ts || row.market_slug || row.slug;
    return <Text className="market-id">{id}</Text>;
  };
  const renderStatusWithReason = (value: string, row: TradeRow) => {
    const tag = renderTradeStatus(value);
    if (!row.skip_reason) return tag;
    return <Tooltip title={row.skip_reason}>{tag}</Tooltip>;
  };
  return (
    <Card className="panel recent-card" title={`最近交易 (${trades.total}/100)`}>
      <Table<TradeRow>
        rowKey={(r, i) => `${r.slug}-${r.time}-${i}`}
        size="small"
        dataSource={trades.trades}
        rowClassName={getRowClassName}
        scroll={{ x: 1760 }}
        pagination={{
          current: page,
          total: trades.total,
          pageSize: 20,
          onChange: setPage,
          showSizeChanger: false,
        }}
        columns={[
          { title: "状态", dataIndex: "status", fixed: "left", width: 86, render: renderStatusWithReason },
          { title: "市场时间", dataIndex: "market_time", width: 135 },
          { title: "市场", dataIndex: "window_start_ts", width: 118, render: renderMarketId },
          { title: "方向", dataIndex: "direction", width: 80, render: renderDirection },
          { title: "开盘价", dataIndex: "btc_open", width: 112, render: (v) => btcPrice(v) },
          { title: "买入BTC", dataIndex: "btc_entry", width: 112, render: (v) => btcPrice(v, "orange strong") },
          { title: "结算价", dataIndex: "btc_final", width: 112, render: renderSettlement },
          { title: "买入价差", dataIndex: "buy_gap", width: 104, render: signedDollar },
          { title: "结算价差", dataIndex: "settlement_gap", width: 104, render: signedDollar },
          { title: "结算方向", dataIndex: "settlement_direction", width: 108, render: renderSettlementWinner },
          { title: "买入概率", dataIndex: "buy_prob", width: 92, render: marketProbability },
          { title: "买入金额", dataIndex: "buy_amount", width: 96, render: compactMoney },
          { title: "手续费", dataIndex: "fee", width: 88, render: (v) => (v ? money(v) : <Text type="secondary">--</Text>) },
          { title: "入场", dataIndex: "entry_seconds_before", width: 78, render: renderEntryTime },
          { title: "盈亏", dataIndex: "net_profit", width: 88, render: renderSettledMoney },
          { title: "盈亏率", dataIndex: "return_pct", width: 88, render: renderSettledPct },
          { title: "说明", dataIndex: "skip_reason", ellipsis: true, render: renderTradeNote },
        ]}
      />
    </Card>
  );
}

function AnalyticsView({ fundTrend, skipReasons, summary }: { 
  fundTrend: {data: Array<{time: string, bankroll: number, pnl: number, slug: string}>, initial: number};
  skipReasons: {data: Array<{name: string, value: number}>, total: number};
  summary: SummaryState | null;
}) {
  // 资金趋势图
  useChart(
    "fundTrendChart",
    {
      backgroundColor: "transparent",
      tooltip: { 
        trigger: "axis",
        formatter: (params: any) => {
          const p = params[0];
          return `${p.name}<br/>资金: $${p.value.toFixed(2)}`;
        }
      },
      xAxis: { 
        type: "category", 
        data: fundTrend.data.map((d) => d.time.slice(5, 16)),
        axisLabel: { rotate: 30 }
      },
      yAxis: { 
        type: "value",
        axisLabel: { formatter: "${value}" }
      },
      series: [
        {
          type: "line",
          smooth: true,
          name: "资金",
          data: fundTrend.data.map((d) => d.bankroll),
          areaStyle: { 
            color: {
              type: "linear",
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(46, 125, 50, 0.3)" },
                { offset: 1, color: "rgba(46, 125, 50, 0.05)" }
              ]
            }
          },
          lineStyle: { color: "#2e7d32", width: 2 },
          itemStyle: { color: "#2e7d32" },
        },
      ],
      grid: { left: 60, right: 20, top: 30, bottom: 60 },
    },
    [fundTrend],
  );

  // 跳过原因饼图
  useChart(
    "skipReasonChart",
    {
      backgroundColor: "transparent",
      tooltip: { 
        trigger: "item",
        formatter: "{b}: {c} ({d}%)"
      },
      legend: {
        orient: "vertical",
        right: 10,
        top: "center",
        textStyle: { color: "#fff" }
      },
      series: [
        {
          type: "pie",
          radius: ["40%", "70%"],
          avoidLabelOverlap: false,
          itemStyle: { borderRadius: 6, borderColor: "#1a1a1a", borderWidth: 2 },
          label: { show: false },
          emphasis: {
            label: { show: true, fontSize: 14, fontWeight: "bold" }
          },
          labelLine: { show: false },
          data: skipReasons.data.map((d, i) => ({
            ...d,
            itemStyle: { color: ["#ff6b6b", "#ffa94d", "#ffd43b", "#69db7c", "#4dabf7", "#9775fa"][i % 6] }
          })),
        },
      ],
    },
    [skipReasons],
  );

  // 交易统计卡片
  const total = summary?.total || 0;
  const confirmed = summary?.confirmed || 0;
  const skipped = summary?.skipped || 0;
  const winRate = summary?.win_rate || 0;

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={16}>
        <Card className="panel" title="资金变化趋势">
          <div id="fundTrendChart" style={{ height: 300 }} />
          <div style={{ marginTop: 16, textAlign: "center" }}>
            <Space size="large">
              <Statistic title="初始资金" value={fundTrend.initial} precision={2} prefix="$" />
              <Statistic title="当前资金" value={fundTrend.data[fundTrend.data.length - 1]?.bankroll || fundTrend.initial} precision={2} prefix="$" />
              <Statistic 
                title="总收益"
                value={(fundTrend.data[fundTrend.data.length - 1]?.bankroll || fundTrend.initial) - fundTrend.initial} 
                precision={2} 
                prefix="$"
                valueStyle={{ color: (fundTrend.data[fundTrend.data.length - 1]?.bankroll || fundTrend.initial) >= fundTrend.initial ? "#3f8600" : "#cf1322" }}
              />
            </Space>
          </div>
        </Card>
      </Col>
      <Col xs={24} xl={8}>
        <Card className="panel" title="跳过原因分布">
          <div id="skipReasonChart" style={{ height: 300 }} />
          <div style={{ marginTop: 16, textAlign: "center" }}>
            <Space size="large">
              <Statistic title="总交易" value={total} />
              <Statistic title="已确认" value={confirmed} />
              <Statistic title="已跳过" value={skipped} />
              <Statistic title="胜率" value={winRate} suffix="%" precision={1} />
            </Space>
          </div>
        </Card>
      </Col>
      <Col xs={24}>
        <Card className="panel" title="交易统计概览">
          <Row gutter={[16, 16]}>
            <Col xs={12} md={6}>
              <Statistic title="总交易数" value={total} />
            </Col>
            <Col xs={12} md={6}>
              <Statistic title="已确认交易" value={confirmed} valueStyle={{ color: "#3f8600" }} />
            </Col>
            <Col xs={12} md={6}>
              <Statistic title="跳过交易" value={skipped} valueStyle={{ color: "#d48806" }} />
            </Col>
            <Col xs={12} md={6}>
              <Statistic title="胜率" value={winRate} suffix="%" precision={1} valueStyle={{ color: winRate > 50 ? "#3f8600" : "#cf1322" }} />
            </Col>
          </Row>
          <Divider />
          <Row gutter={[16, 16]}>
            <Col xs={12} md={6}>
              <Statistic title="总盈亏" value={summary?.total_pnl || 0} precision={2} prefix="$" valueStyle={{ color: (summary?.total_pnl || 0) >= 0 ? "#3f8600" : "#cf1322" }} />
            </Col>
            <Col xs={12} md={6}>
              <Statistic title="总投入" value={summary?.total_amount || 0} precision={2} prefix="$" />
            </Col>
            <Col xs={12} md={6}>
              <Statistic title="盈利次数" value={summary?.won || 0} valueStyle={{ color: "#3f8600" }} />
            </Col>
            <Col xs={12} md={6}>
              <Statistic title="亏损次数" value={summary?.lost || 0} valueStyle={{ color: "#cf1322" }} />
            </Col>
          </Row>
        </Card>
      </Col>
    </Row>
  );
}

function UserCenter({
  safety,
  status,
  wallet,
  dataQuality,
  onRefresh,
  children,
}: {
  safety: SafetyState | null;
  status: StatusState | null;
  wallet: WalletState | null;
  dataQuality: DataQualityState | null;
  onRefresh: () => Promise<void>;
  children?: React.ReactNode;
}) {
  const { message } = AntApp.useApp();
  const checks = safety?.checks || [];
  const okCount = checks.filter((c) => c.ok).length;
  const refreshBackend = async () => {
    await api.refreshBackend();
    await onRefresh();
    message.success("后端状态已刷新");
  };
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={7}>
        <Card className="panel" title="连接状态">
          <Progress percent={checks.length ? Math.round((okCount / checks.length) * 100) : 0} />
          <Space direction="vertical" className="full">
            {checks.map((c) => (
              <Health key={c.name} ok={c.ok} text={c.name} />
            ))}
          </Space>
          <Button className="wide-link" icon={<ReloadOutlined />} onClick={refreshBackend}>
            刷新后端状态
          </Button>
        </Card>
      </Col>
      <Col xs={24} xl={10}>
        <Card className="panel" title="实盘资金">
          <Descriptions column={1} size="small">
            <Descriptions.Item label="下单方式">{wallet?.route || safety?.executor || "--"}</Descriptions.Item>
            <Descriptions.Item label="网络">{wallet ? `${wallet.network} / ${wallet.chain_id}` : "--"}</Descriptions.Item>
            <Descriptions.Item label="控制钱包">{wallet?.signer || "--"}</Descriptions.Item>
            <Descriptions.Item label="实盘收款钱包">{wallet?.deposit_wallet_short || "--"}</Descriptions.Item>
            <Descriptions.Item label="钱包里真金">{money(wallet?.chain_pUSD_balance)}</Descriptions.Item>
            <Descriptions.Item label="可下单余额">{money(wallet?.clob_balance)}</Descriptions.Item>
            <Descriptions.Item label="手续费币">{wallet?.native_pol ?? 0} POL（这条路线通常不需要）</Descriptions.Item>
          </Descriptions>
          <Space wrap className="wallet-actions">
            <Button href={wallet?.deposit_wallet_url} target="_blank" disabled={!wallet?.deposit_wallet_url} icon={<WalletOutlined />}>
              查看实盘钱包
            </Button>
            <Button href={wallet?.pUSD_token_url} target="_blank" disabled={!wallet?.pUSD_token_url} icon={<ExportOutlined />}>
              查看资金合约
            </Button>
          </Space>
        </Card>
      </Col>
      <Col xs={24} xl={7}>
        <Card className="panel" title="自动下单状态">
          <Space direction="vertical">
            <Tag icon={<SafetyCertificateOutlined />} color="blue">
              使用你自己的钱包签名
            </Tag>
            <Tag icon={<CheckCircleFilled />} color={wallet?.allowance_ready ? "green" : "orange"}>
              已允许程序扣款下单
            </Tag>
            <Tag color={wallet?.last_order?.status === "matched" ? "green" : "default"}>
              最近真实订单：{wallet?.last_order?.status === "matched" ? "已成交" : wallet?.last_order?.status || "暂无"}
            </Tag>
            <Text type="secondary">下一步把已验证的下单方式接入自动循环。</Text>
          </Space>
        </Card>
      </Col>
      <Col span={24}>
        <Card className="panel" title="数据质量">
          <DataQualityCard dataQuality={dataQuality} />
        </Card>
      </Col>
      {children ? <Col span={24}>{children}</Col> : null}
      <Col span={24}>
        <Card className="panel" title="充值、授权、真实订单记录">
          <Table<BackendEvent>
            rowKey={(r, i) => `${r.type}-${r.time}-${i}`}
            size="small"
            dataSource={wallet?.events || []}
            pagination={false}
            scroll={{ x: 1100 }}
            columns={[
              { title: "市场时间", dataIndex: "market_time", width: 135 },
              { title: "类型", dataIndex: "type", width: 105, render: renderEventType },
              { title: "状态", dataIndex: "status", width: 96, render: renderEventStatus },
              { title: "金额", dataIndex: "amount", width: 110, render: (v, r) => (v ? `${money(v)} ${r.asset || ""}` : r.asset || "--") },
              { title: "方向", dataIndex: "direction", width: 80, render: (v) => (v ? renderDirection(v) : "--") },
              { title: "价格", dataIndex: "price", width: 80 },
              { title: "份额", dataIndex: "shares", width: 90 },
              { title: "订单/授权编号", width: 190, render: (_, r) => <ShortHash value={r.order_id || r.relayer_tx_id || ""} /> },
              { title: "Polygonscan", dataIndex: "tx_url", width: 120, render: renderTx },
              { title: "说明", dataIndex: "note", ellipsis: true },
            ]}
          />
        </Card>
      </Col>
    </Row>
  );
}

function Health({ ok, text }: { ok: boolean; text: string }) {
  return <Tag color={ok ? "success" : "error"}>{ok ? "已连接" : "未连接"} / {text}</Tag>;
}

function calcWinRate(status: StatusState | null) {
  const total = status?.stats?.total;
  if (total) return total.win_rate || 0;
  const t = status?.trader_state.trade_count || 0;
  return t ? ((status?.trader_state.win_count || 0) / t) * 100 : 0;
}

function renderDirection(value: string) {
  const v = String(value || "").toLowerCase();
  if (v === "up") return <Tag color="success">Up</Tag>;
  if (v === "down") return <Tag color="error">Down</Tag>;
  return <Tag color="default">--</Tag>;
}

function renderSettlementWinner(value: string, record: any) {
  const v = String(value || "").toLowerCase();
  const dir = String(record?.direction || "").toLowerCase();
  if (!v) return <Text type="secondary">--</Text>;
  const won = v === dir;
  if (v === "up") return <Tag color={won ? "success" : "warning"}>Up {won ? "赢" : "输"}</Tag>;
  if (v === "down") return <Tag color={won ? "success" : "warning"}>Down {won ? "赢" : "输"}</Tag>;
  return <Tag color="default">--</Tag>;
}

function renderTradeStatus(value: string) {
  if (value === "won") return <Tag color="success">盈利</Tag>;
  if (value === "failed" || value === "lost" || value === "matched_lost") return <Tag color="error">亏损</Tag>;
  if (value === "pending") return <Tag color="processing">待结算</Tag>;
  if (value === "skipped") return <Tag color="default">跳过</Tag>;
  return <Tag color="default">跳过</Tag>;
}

function getRowClassName(record: TradeRow): string {
  if (record.status === "won") return "row-won";
  if (record.status === "lost" || record.status === "failed") return "row-lost";
  if (record.status === "skipped") return "row-skipped";
  if (record.status === "pending") return "row-pending";
  return "";
}

function renderMode(value: string) {
  if (value === "live") return <Tag color="red">实盘</Tag>;
  return <Tag color="blue">模拟</Tag>;
}
function renderEventType(value: string) {
  const color = value === "order" ? "blue" : value === "deposit" ? "green" : "purple";
  const text = value === "order" ? "订单" : value === "deposit" ? "入金" : "授权";
  return <Tag color={color}>{text}</Tag>;
}

function renderEventStatus(value: string) {
  const ok = ["confirmed", "matched", "success"].includes(String(value).toLowerCase());
  return <Tag color={ok ? "success" : "warning"}>{value || "--"}</Tag>;
}

function renderTx(value: string) {
  if (!value) return <Text type="secondary">--</Text>;
  return (
    <Button type="link" size="small" href={value} target="_blank" icon={<ExportOutlined />}>
      查看
    </Button>
  );
}

function ShortHash({ value }: { value?: string }) {
  if (!value) return <Text type="secondary">--</Text>;
  return (
    <Tooltip title={value}>
      <Text code>{value.length > 20 ? `${value.slice(0, 10)}...${value.slice(-6)}` : value}</Text>
    </Tooltip>
  );
}

function signedMoney(v: number | string | null) {
  if (v === null || v === undefined || v === "") return <Typography.Text type="secondary">--</Typography.Text>;
  const n = Number(v || 0);
  if (!Number.isFinite(n) || n === 0) return <Typography.Text type="secondary">--</Typography.Text>;
  return <span className={n >= 0 ? "green" : "red"}>{n >= 0 ? "+" : ""}{compactMoney(n)}</span>;
}

createRoot(document.getElementById("root")!).render(<AppShell />);
