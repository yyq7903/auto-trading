#!/usr/bin/env python3
"""
api_server.py — WebUI API 服务器
提供静态文件 + 配置读写API + 交易状态API + 每日汇总
端口: 8877
"""
import json
import time
import re
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from datetime import datetime, timezone, timedelta

WEBUI_DIR = Path("/home/yyq/workspace/btc5m-webui")
TRADER_DIR = Path("/home/yyq/workspace/btc5m-trader")
DATA_DIR = Path("/mnt/c/Users/yyq/Desktop/polymarket项目/btc5m数据")
CN = timezone(timedelta(hours=8))


class APIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEBUI_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/api/config":
            self._serve_json(TRADER_DIR / "config.json")
        elif self.path == "/api/trader":
            self._serve_trader()
        elif self.path == "/api/summary":
            self._serve_summary()
        elif self.path == "/api/live":
            self._serve_live()
        elif self.path == "/api/status":
            self._serve_status()
        elif self.path == "/api/btc-history":
            self._serve_btc_history()
        elif self.path == "/api/performance":
            self._serve_performance()
        elif self.path == "/api/strategies":
            self._serve_strategies()
        elif self.path == "/api/polymarket-balance":
            self._serve_polymarket_balance()
        elif self.path.startswith("/api/trades"):
            self._serve_trades()
        elif self.path == "/data.json":
            # data.json 缓存 3 秒
            self._serve_cached_json(WEBUI_DIR / "data.json", max_age=3)
        else:
            # 静态文件（JS/CSS）缓存 1 小时
            if self.path.endswith(('.js', '.css', '.png', '.ico')):
                self.send_response(200)
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/config":
            self._update_config()
        elif self.path == "/api/toggle":
            self._toggle_running()
        elif self.path == "/api/reset":
            self._reset_capital()
        elif self.path == "/api/refresh":
            self._refresh_data()
        elif self.path == "/api/strategies/switch":
            self._switch_strategy()
        elif self.path == "/api/strategies/update":
            self._update_strategy()
        else:
            self.send_error(404)

    def _serve_json(self, path):
        try:
            with open(path) as f:
                data = json.load(f)
            self._json_response(data)
        except FileNotFoundError:
            self._json_response({"error": "not found"}, 404)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _serve_cached_json(self, path, max_age=5):
        """带缓存头的 JSON 响应"""
        try:
            with open(path) as f:
                data = json.load(f)
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.send_header("Cache-Control", f"public, max-age={max_age}")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass
        except FileNotFoundError:
            self._json_response({"error": "not found"}, 404)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _serve_live(self):
        """实时状态：当前市场 + BTC价格 + 倒计时"""
        now = int(time.time())
        current_5m = (now // 300) * 300
        sec_left = current_5m + 300 - now
        slug = f"btc-updown-5m-{current_5m}"

        # 读最新 BTC 价格（只读最后一行）
        btc_price = 0
        ptb = 0
        up_price = 0
        down_price = 0
        market_slug = ""
        try:
            # 使用 tail 命令快速读取最后一行
            import subprocess
            result = subprocess.run(
                ["tail", "-n", "1", str(DATA_DIR / "btc_price.jsonl")],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                last = json.loads(result.stdout.strip())
                btc_price = last.get("chainlink_price", 0)
                ptb = last.get("price_to_beat", 0)
                up_price = last.get("up_price", 0)
                down_price = last.get("down_price", 0)
                market_slug = last.get("slug", "")
        except:
            pass

        gap = round(btc_price - ptb, 2) if btc_price and ptb else 0

        self._json_response({
            "time": datetime.now(CN).strftime("%H:%M:%S"),
            "slug": slug,
            "market_slug": market_slug,
            "sec_left": sec_left,
            "btc_price": round(btc_price, 2),
            "ptb": round(ptb, 2),
            "gap": gap,
            "up_price": round(up_price, 3),
            "down_price": round(down_price, 3),
        })

    def _check_trader_service(self):
        try:
            import subprocess
            result = subprocess.run(
                ["systemctl", "--user", "is-active", "btc5m-trader"],
                capture_output=True, text=True, timeout=3
            )
            return result.stdout.strip() == "active"
        except:
            return False

    def _serve_trader(self):
        """聚合 trader 状态 + 最近交易 + 当前配置"""
        state = {}
        try:
            with open(DATA_DIR / "trader_state.json") as f:
                state = json.load(f)
        except:
            pass

        trades = []
        try:
            # 只读最后100行，避免读取整个文件
            import subprocess
            result = subprocess.run(
                ["tail", "-n", "100", str(DATA_DIR / "trades.jsonl")],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    line = line.strip()
                    if line:
                        try:
                            trades.append(json.loads(line))
                        except:
                            pass
        except:
            pass

        config = {}
        try:
            with open(TRADER_DIR / "config.json") as f:
                config = json.load(f)
        except:
            pass

        notifies = []
        try:
            with open(DATA_DIR / "trader_notify.txt") as f:
                notifies = [l.strip() for l in f.readlines()[-20:] if l.strip()]
        except:
            pass

        now = int(time.time())

        # 读取双状态数据（兼容嵌套和扁平格式）
        if state and "bankroll" in state and "sim_state" not in state:
            sim_state = {}
            live_state_data = state
        else:
            sim_state = state.get("sim_state", {})
            live_state_data = state.get("live_state", {})
        
        output = {
            "last_update": datetime.now(CN).strftime("%Y-%m-%d %H:%M:%S"),
            "mode": config.get("mode", "sim"),
            # 当前模式的数据
            "bankroll": (live_state_data.get("bankroll", 1.01) if config.get("mode") == "live" else sim_state.get("bankroll", 1.0)),
            "total_withdrawn": (live_state_data.get("total_withdrawn", 0.0) if config.get("mode") == "live" else sim_state.get("total_withdrawn", 0.0)),
            "trade_count": (live_state_data.get("trade_count", 0) if config.get("mode") == "live" else sim_state.get("trade_count", 0)),
            "win_count": (live_state_data.get("win_count", 0) if config.get("mode") == "live" else sim_state.get("win_count", 0)),
            "loss_count": (live_state_data.get("loss_count", 0) if config.get("mode") == "live" else sim_state.get("loss_count", 0)),
            "consecutive_losses": state.get("consecutive_losses", 0),
            "cooldown_until": state.get("cooldown_until", 0),
            # 模拟盘独立数据
            "sim_bankroll": sim_state.get("bankroll", 1.0),
            "sim_trade_count": sim_state.get("trade_count", 0),
            "sim_win_count": sim_state.get("win_count", 0),
            "sim_loss_count": sim_state.get("loss_count", 0),
            "sim_total_withdrawn": sim_state.get("total_withdrawn", 0.0),
            # 实盘独立数据
            "live_bankroll": live_state_data.get("bankroll", 1.01),
            "live_trade_count": live_state_data.get("trade_count", 0),
            "live_win_count": live_state_data.get("win_count", 0),
            "live_loss_count": live_state_data.get("loss_count", 0),
            "live_total_withdrawn": live_state_data.get("total_withdrawn", 0.0),
            # 通用
            "service_active": self._check_trader_service(),
            "paused": config.get("paused", True),
            "config": config,
            "trades": trades[-50:],
            "notifies": notifies,
        }
        self._json_response(output)

    def _trade_status(self, trade, now):
        """判断交易状态: pending / won / lost"""
        slug = trade.get("slug", "")
        m = re.search(r'(\d{10,})$', slug)
        if not m:
            return "won" if trade.get("won") else "lost"
        market_end = int(m.group(1)) + 300
        # 市场结束后30秒内视为等待结算
        if now < market_end + 30:
            return "pending"
        return "won" if trade.get("won") else "lost"

    def _calc_daily_summary(self, trades):
        """按天聚合交易统计（跳过的订单单独统计）"""
        if not trades:
            return []

        days = {}
        for t in trades:
            time_str = t.get("time", "")
            if not time_str:
                continue
            date = time_str[:10]  # YYYY-MM-DD
            if date not in days:
                days[date] = {
                    "date": date,
                    "trades": 0,      # 执行的交易数
                    "skipped": 0,     # 跳过的订单数
                    "wins": 0,
                    "losses": 0,
                    "pnl": 0.0,
                    "best": 0.0,
                    "worst": 0.0,
                    "mode": t.get("mode", "sim"),
                }
            d = days[date]
            
            # 跳过的订单单独计数
            if t.get("status") == "skipped":
                d["skipped"] += 1
                continue
            
            # 只有执行的交易才计入统计
            d["trades"] += 1
            pnl = t.get("net_profit", 0)
            d["pnl"] += pnl
            if t.get("won"):
                d["wins"] += 1
            else:
                d["losses"] += 1
            d["best"] = max(d["best"], pnl)
            d["worst"] = min(d["worst"], pnl)
            if t.get("mode") == "live":
                d["mode"] = "live"

        result = []
        for date in sorted(days.keys(), reverse=True):
            d = days[date]
            d["pnl"] = round(d["pnl"], 2)
            d["best"] = round(d["best"], 2)
            d["worst"] = round(d["worst"], 2)
            d["win_rate"] = round(d["wins"] / d["trades"] * 100, 1) if d["trades"] > 0 else 0
            result.append(d)

        return result

    def _serve_summary(self):
        """独立的每日汇总接口"""
        trades = []
        try:
            import subprocess
            result = subprocess.run(
                ["tail", "-n", "200", str(DATA_DIR / "trades.jsonl")],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    line = line.strip()
                    if line:
                        try:
                            trades.append(json.loads(line))
                        except:
                            pass
        except:
            pass
        self._json_response({"daily_summary": self._calc_daily_summary(trades)})

    def _serve_btc_history(self):
        """最近5分钟的 BTC 价格历史（每5秒一个点）"""
        prices = []
        try:
            # 使用 tail 命令快速读取最后300行
            import subprocess
            result = subprocess.run(
                ["tail", "-n", "300", str(DATA_DIR / "btc_price.jsonl")],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        try:
                            d = json.loads(line)
                            cl = d.get("chainlink_price", 0)
                            ts = d.get("timestamp", "")
                            if cl > 0 and ts:
                                prices.append({
                                    "t": ts[11:19],  # HH:MM:SS
                                    "p": round(cl, 2),
                                    "ptb": round(d.get("price_to_beat", 0), 2),
                                    "up": round(d.get("up_price", 0), 3),
                                    "down": round(d.get("down_price", 0), 3),
                                })
                        except:
                            pass
        except:
            pass
        # 每5秒取一个点（减少数据量）
        sampled = prices[::5] if len(prices) > 60 else prices
        self._json_response({"prices": sampled})

    def _serve_performance(self):
        """性能指标：最大回撤、连胜连亏、资金曲线"""
        trades = []
        try:
            import subprocess
            result = subprocess.run(
                ["tail", "-n", "500", str(DATA_DIR / "trades.jsonl")],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    line = line.strip()
                    if line:
                        try:
                            t = json.loads(line)
                            if t.get("status") != "skipped":
                                trades.append(t)
                        except:
                            pass
        except:
            pass

        if not trades:
            self._json_response({
                "max_drawdown": 0,
                "max_drawdown_pct": 0,
                "current_streak": 0,
                "max_win_streak": 0,
                "max_loss_streak": 0,
                "equity_curve": [],
                "total_pnl": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "profit_factor": 0,
            })
            return

        # 资金曲线
        equity_curve = []
        capital = 10.0  # 初始资金
        peak = capital
        max_dd = 0
        max_dd_pct = 0

        for t in trades:
            pnl = t.get("net_profit", 0)
            capital += pnl
            capital = max(0, capital)
            peak = max(peak, capital)
            dd = peak - capital
            dd_pct = (dd / peak * 100) if peak > 0 else 0
            max_dd = max(max_dd, dd)
            max_dd_pct = max(max_dd_pct, dd_pct)
            equity_curve.append({
                "time": t.get("time", "")[11:19],
                "value": round(capital, 2),
                "pnl": round(pnl, 2),
            })

        # 连胜/连亏
        max_win_streak = 0
        max_loss_streak = 0
        current_streak = 0
        streak_type = None
        wins = []
        losses = []

        for t in trades:
            if t.get("won"):
                wins.append(t.get("net_profit", 0))
                if streak_type == "win":
                    current_streak += 1
                else:
                    current_streak = 1
                    streak_type = "win"
                max_win_streak = max(max_win_streak, current_streak)
            else:
                losses.append(t.get("net_profit", 0))
                if streak_type == "loss":
                    current_streak += 1
                else:
                    current_streak = 1
                    streak_type = "loss"
                max_loss_streak = max(max_loss_streak, current_streak)

        # 当前连胜/连亏
        current_streak_val = current_streak if streak_type else 0
        if streak_type == "loss":
            current_streak_val = -current_streak_val

        # 平均盈亏
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        # 盈亏比
        total_win = sum(wins)
        total_loss = abs(sum(losses))
        profit_factor = total_win / total_loss if total_loss > 0 else float('inf')

        self._json_response({
            "max_drawdown": round(max_dd, 2),
            "max_drawdown_pct": round(max_dd_pct, 1),
            "current_streak": current_streak_val,
            "max_win_streak": max_win_streak,
            "max_loss_streak": max_loss_streak,
            "equity_curve": equity_curve,
            "total_pnl": round(capital - 10.0, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else 999,
        })

    def _serve_status(self):
        """双环境状态"""
        import subprocess

        def svc_active(name):
            try:
                r = subprocess.run(["systemctl", "--user", "is-active", name], capture_output=True, text=True, timeout=3)
                return r.stdout.strip() == "active"
            except:
                return False

        sim_config = {}
        live_config = {}
        try:
            with open(TRADER_DIR / "sim" / "config.json") as f:
                sim_config = json.load(f)
        except:
            pass
        try:
            with open(TRADER_DIR / "live" / "config.json") as f:
                live_config = json.load(f)
        except:
            pass

        # 浏览器执行器状态
        browser_ready = False
        try:
            import requests
            r = requests.get("http://172.18.16.1:8789/status", timeout=2)
            if r.status_code == 200:
                browser_ready = r.json().get("ready", False)
        except:
            pass

        # Sim/Live 状态
        sim_state = {}
        try:
            with open(f"/mnt/c/Users/yyq/Desktop/polymarket项目/btc5m数据/sim/state.json") as f:
                sim_state = json.load(f)
        except:
            pass
        live_state = {}
        try:
            with open(f"/home/yyq/workspace/btc5m-trader/live/state.json") as f:
                live_state = json.load(f)
        except:
            pass

        self._json_response({
            "sim": {
                "service_active": svc_active("btc5m-sim"),
                "paused": sim_config.get("paused", True),
                "state": sim_state,
            },
            "live": {
                "service_active": svc_active("btc5m-live"),
                "paused": live_config.get("paused", True),
                "state": live_state,
                "browser_ready": browser_ready,
            },
            "executor_mode": "browser",
        })

    def _toggle_running(self):
        """启动/停止交易机器人"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            action = data.get("action", "toggle")  # "start" / "stop" / "toggle"

            config_path = TRADER_DIR / "config.json"
            with open(config_path) as f:
                config = json.load(f)

            if action == "start":
                config["paused"] = False
            elif action == "stop":
                config["paused"] = True
            else:  # toggle
                config["paused"] = not config.get("paused", True)

            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)

            status = "运行中" if not config["paused"] else "已暂停"
            self._json_response({"ok": True, "paused": config["paused"], "status": status})
        except Exception as e:
            self._json_response({"error": str(e)}, 400)

    def _reset_capital(self):
        """重置资金到初始值"""
        try:
            config = {}
            with open(TRADER_DIR / "config.json") as f:
                config = json.load(f)

            ic = config.get("initial_capital", 10.0)

            state = {
                "bankroll": ic,
                "total_withdrawn": 0,
                "trade_count": 0,
                "win_count": 0,
                "loss_count": 0,
                "consecutive_losses": 0,
                "cooldown_until": 0,
            }
            with open(DATA_DIR / "trader_state.json", "w") as f:
                json.dump(state, f)

            # 清空交易记录
            with open(DATA_DIR / "trades.jsonl", "w") as f:
                pass

            # 清空通知
            with open(DATA_DIR / "trader_notify.txt", "w") as f:
                pass

            self._json_response({"ok": True, "bankroll": ic, "message": f"已重置: ${ic:.2f}"})
        except Exception as e:
            self._json_response({"error": str(e)}, 400)

    def _refresh_data(self):
        """手动刷新 data.json"""
        try:
            import subprocess
            result = subprocess.run(
                ["python3", str(WEBUI_DIR / "prepare.py")],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                # 读取生成的 data.json 统计
                with open(WEBUI_DIR / "data.json") as f:
                    data = json.load(f)
                self._json_response({
                    "ok": True,
                    "markets": len(data),
                    "message": f"已刷新 {len(data)} 个市场"
                })
            else:
                self._json_response({"error": result.stderr[-200:]}, 500)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _update_config(self):
        """更新交易机器人配置（兼容新旧格式）"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            new_config = json.loads(body)

            config_path = TRADER_DIR / "config.json"
            with open(config_path) as f:
                current = json.load(f)

            # 检查是否是新格式
            if "strategies" in current:
                # 新格式：更新全局配置和当前策略参数
                active_id = current.get("active_strategy", "1")
                
                # 更新全局配置
                global_keys = {"withdraw_mode", "max_consecutive_losses", "mode", "initial_capital", "paused"}
                for k, v in new_config.items():
                    if k in global_keys:
                        current[k] = v
                
                # 更新当前策略参数
                strategy_params = {"entry_second", "gap_threshold", "min_buy_price", "bet_fraction", "cooldown_seconds"}
                if active_id in current["strategies"]:
                    for k, v in new_config.items():
                        if k in strategy_params:
                            current["strategies"][active_id]["params"][k] = v
                
                # 验证范围
                if active_id in current["strategies"]:
                    params = current["strategies"][active_id]["params"]
                    params["entry_second"] = max(5, min(60, int(params.get("entry_second", 25))))
                    params["gap_threshold"] = max(0, min(100, int(params.get("gap_threshold", 10))))
                    params["min_buy_price"] = max(0.50, min(0.95, float(params.get("min_buy_price", 0.60))))
                    bf = float(params.get("bet_fraction", 0.50))
                    params["bet_fraction"] = bf if bf in (1.0, 0.50, 0.25) else 0.50
                    params["cooldown_seconds"] = max(0, min(3600, int(params.get("cooldown_seconds", 0))))
            else:
                # 旧格式：直接更新
                allowed = {
                    "entry_second", "gap_threshold", "min_buy_price",
                    "bet_fraction", "withdraw_mode", "max_consecutive_losses",
                    "cooldown_seconds", "mode", "initial_capital", "paused"
                }
                for k, v in new_config.items():
                    if k in allowed:
                        current[k] = v

                current["entry_second"] = max(5, min(60, int(current.get("entry_second", 25))))
                current["gap_threshold"] = max(0, min(100, int(current.get("gap_threshold", 10))))
                current["min_buy_price"] = max(0.50, min(0.95, float(current.get("min_buy_price", 0.60))))
                bf = float(current.get("bet_fraction", 0.50))
                current["bet_fraction"] = bf if bf in (1.0, 0.50, 0.25) else 0.50
                wm = current.get("withdraw_mode", "none")
                current["withdraw_mode"] = wm if wm in ("none", "half", "all") else "none"
                current["max_consecutive_losses"] = max(1, min(5, int(current.get("max_consecutive_losses", 1))))
                current["cooldown_seconds"] = max(0, min(3600, int(current.get("cooldown_seconds", 0))))
                mode = current.get("mode", "sim")
                current["mode"] = mode if mode in ("sim", "live") else "sim"
                current["initial_capital"] = max(1, min(10000, float(current.get("initial_capital", 10))))

            with open(config_path, "w") as f:
                json.dump(current, f, indent=2, ensure_ascii=False)

            self._json_response({"ok": True, "config": current})
        except Exception as e:
            self._json_response({"error": str(e)}, 400)

    def _serve_strategies(self):
        """获取所有策略信息"""
        try:
            config_path = TRADER_DIR / "config.json"
            with open(config_path) as f:
                config = json.load(f)
            
            if "strategies" in config:
                result = {
                    "strategies": config["strategies"],
                    "active_strategy": config.get("active_strategy", "1")
                }
            else:
                # 旧格式，返回单策略
                result = {
                    "strategies": {
                        "1": {
                            "name": "策略一（默认）",
                            "params": {
                                "entry_second": config.get("entry_second", 25),
                                "gap_threshold": config.get("gap_threshold", 10),
                                "min_buy_price": config.get("min_buy_price", 0.60),
                                "bet_fraction": config.get("bet_fraction", 1.0),
                                "cooldown_seconds": config.get("cooldown_seconds", 0)
                            }
                        }
                    },
                    "active_strategy": "1"
                }
            
            self._json_response(result)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _serve_trades(self):
        """获取交易记录，支持 ?mode=sim|live 参数"""
        import urllib.parse
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        mode = params.get("mode", ["sim"])[0]
        trades_file = f"/mnt/c/Users/yyq/Desktop/polymarket项目/btc5m数据/{mode}/trades.jsonl"
        trades = []
        try:
            with open(trades_file) as f:
                for line in f:
                    if line.strip():
                        try:
                            trades.append(json.loads(line))
                        except:
                            pass
        except:
            pass
        self._json_response(trades)

    def _switch_strategy(self):
        """切换活跃策略"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            strategy_id = data.get("strategy_id")
            
            if not strategy_id:
                self._json_response({"error": "缺少strategy_id"}, 400)
                return
            
            config_path = TRADER_DIR / "config.json"
            with open(config_path) as f:
                config = json.load(f)
            
            if "strategies" not in config:
                self._json_response({"error": "配置格式不支持多策略"}, 400)
                return
            
            if strategy_id not in config["strategies"]:
                self._json_response({"error": f"策略{strategy_id}不存在"}, 404)
                return
            
            config["active_strategy"] = strategy_id
            
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            strategy_name = config["strategies"][strategy_id].get("name", f"策略{strategy_id}")
            self._json_response({
                "ok": True, 
                "active_strategy": strategy_id,
                "message": f"已切换到 [{strategy_name}]"
            })
        except Exception as e:
            self._json_response({"error": str(e)}, 400)

    def _update_strategy(self):
        """更新策略配置"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            
            strategy_id = data.get("strategy_id")
            name = data.get("name")
            params = data.get("params")
            win_rate = data.get("win_rate")
            
            if not strategy_id:
                self._json_response({"error": "缺少strategy_id"}, 400)
                return
            
            config_path = TRADER_DIR / "config.json"
            with open(config_path) as f:
                config = json.load(f)
            
            if "strategies" not in config:
                self._json_response({"error": "配置格式不支持多策略"}, 400)
                return
            
            if strategy_id not in config["strategies"]:
                self._json_response({"error": f"策略{strategy_id}不存在"}, 404)
                return
            
            # 更新名称
            if name is not None:
                config["strategies"][strategy_id]["name"] = name
            
            # 更新胜率
            if win_rate is not None:
                config["strategies"][strategy_id]["win_rate"] = float(win_rate)
            
            # 更新参数
            if params is not None:
                for k, v in params.items():
                    config["strategies"][strategy_id]["params"][k] = v
                
                # 验证范围
                p = config["strategies"][strategy_id]["params"]
                p["entry_second"] = max(5, min(60, int(p.get("entry_second", 25))))
                p["gap_threshold"] = max(0, min(100, int(p.get("gap_threshold", 10))))
                p["min_buy_price"] = max(0.50, min(0.95, float(p.get("min_buy_price", 0.60))))
                bf = float(p.get("bet_fraction", 0.50))
                p["bet_fraction"] = bf if bf in (1.0, 0.50, 0.25) else 0.50
                p["cooldown_seconds"] = max(0, min(3600, int(p.get("cooldown_seconds", 0))))
            
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            self._json_response({
                "ok": True,
                "strategy": config["strategies"][strategy_id],
                "message": f"策略已更新"
            })
        except Exception as e:
            self._json_response({"error": str(e)}, 400)

    def _serve_polymarket_balance(self):
        """查询Polymarket账户余额"""
        try:
            # 从.env读取钱包地址
            env_path = TRADER_DIR / ".env"
            address = ""
            with open(env_path) as f:
                for line in f:
                    if line.startswith("FUNDER_ADDRESS="):
                        address = line.strip().split("=", 1)[1]
                        break
            
            if not address:
                self._json_response({"error": "未配置钱包地址"}, 400)
                return
            
            # 查询链上USDC余额
            USDC_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
            RPC = "https://polygon-bor-rpc.publicnode.com"
            data = f"0x70a08231000000000000000000000000{address[2:].lower()}"
            
            import requests
            payload = {
                "jsonrpc": "2.0",
                "method": "eth_call",
                "params": [{"to": USDC_CONTRACT, "data": data}, "latest"],
                "id": 1
            }
            resp = requests.post(RPC, json=payload, timeout=10)
            result = resp.json().get("result", "0x0")
            balance = int(result, 16) / 1e6  # USDC has 6 decimals
            
            # 查询MATIC余额
            payload2 = {
                "jsonrpc": "2.0",
                "method": "eth_getBalance",
                "params": [address, "latest"],
                "id": 2
            }
            resp2 = requests.post(RPC, json=payload2, timeout=10)
            result2 = resp2.json().get("result", "0x0")
            matic_balance = int(result2, 16) / 1e18
            
            self._json_response({
                "address": address,
                "usdc_balance": round(balance, 2),
                "matic_balance": round(matic_balance, 4),
                "polymarket_balance": 0.0,  # 平台余额无法查询
                "total_balance": round(balance, 2)
            })
        except Exception as e:
            print(f"查询余额失败: {e}")
            self._json_response({"error": str(e)}, 500)


    def _json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass  # 客户端断开连接，忽略错误

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        if args and "200" not in str(args[1] if len(args) > 1 else ""):
            super().log_message(format, *args)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    port = 8877
    server = ThreadedHTTPServer(("0.0.0.0", port), APIHandler)
    print(f"[{datetime.now(CN).strftime('%H:%M:%S')}] API 服务器启动 http://0.0.0.0:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.server_close()
