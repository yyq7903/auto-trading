"""
Config 管理 — 隔离的 sim/live 配置
"""
import json, os, time, copy
from pathlib import Path

# === 默认策略参数 ===
DEFAULT_CONFIG = {
    "paused": False,
    "armed": False,
    "entry_second": 25,
    "gap_threshold": 10,
    "min_buy_price": 0.60,
    "bet_mode": "fraction",
    "fixed_bet_amount": 1.0,
    "bet_fraction": 1.0,
    "max_live_amount": 1.0,
    "withdraw_mode": "none",
    "max_consecutive_losses": 1,
    "cooldown_seconds": 0,
    "initial_capital": 1.0,
}

DEFAULT_STRATEGIES = {
    "1": {
        "name": "策略一（默认）",
        "win_rate": 95.4,
        "params": {"entry_second": 25, "gap_threshold": 10, "min_buy_price": 0.60, "bet_mode": "fraction", "fixed_bet_amount": 1.0, "bet_fraction": 1.0, "cooldown_seconds": 0},
    },
    "2": {
        "name": "策略二（早段极端动量）",
        "win_rate": 100.0,
        "params": {"entry_second": 120, "gap_threshold": 120, "min_buy_price": 0.70, "bet_mode": "fraction", "fixed_bet_amount": 1.0, "bet_fraction": 0.5, "cooldown_seconds": 0},
    },
    "3": {
        "name": "策略三（中段趋势延续）",
        "win_rate": 99.7,
        "params": {"entry_second": 60, "gap_threshold": 60, "min_buy_price": 0.65, "bet_mode": "fraction", "fixed_bet_amount": 1.0, "bet_fraction": 0.75, "cooldown_seconds": 0},
    },
    "4": {
        "name": "策略四（盘口确认）",
        "win_rate": 99.2,
        "params": {"entry_second": 45, "gap_threshold": 30, "min_buy_price": 0.62, "bet_mode": "fraction", "fixed_bet_amount": 1.0, "bet_fraction": 0.5, "cooldown_seconds": 0},
    },
    "5": {
        "name": "策略五（末秒高置信）",
        "win_rate": 98.9,
        "params": {"entry_second": 15, "gap_threshold": 25, "min_buy_price": 0.75, "bet_mode": "fraction", "fixed_bet_amount": 1.0, "bet_fraction": 0.25, "cooldown_seconds": 0},
    },
}


class Config:
    def __init__(self, config_dir: str):
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / "config.json"
        self.state_file = self.config_dir / "state.json"
        self.data = dict(DEFAULT_CONFIG)
        self.strategies = dict(DEFAULT_STRATEGIES)
        self.active_strategy = "1"
        self.load()

    def load(self):
        if self.config_file.exists():
            try:
                with open(self.config_file) as f:
                    cfg = json.load(f)
                self.data.update(cfg)
                self.strategies = cfg.get("strategies", dict(DEFAULT_STRATEGIES))
                self.active_strategy = cfg.get("active_strategy", "1")
                # Apply active strategy params
                if self.active_strategy in self.strategies:
                    p = self.strategies[self.active_strategy]["params"]
                    for k, v in p.items():
                        self.data[k] = v
            except Exception as e:
                print(f"[Config] 加载失败: {e}")

    def save(self):
        payload = {
            "paused": self.data["paused"],
            "armed": self.data.get("armed", False),
            "entry_second": self.data["entry_second"],
            "gap_threshold": self.data["gap_threshold"],
            "min_buy_price": self.data["min_buy_price"],
            "bet_mode": self.data.get("bet_mode", "fraction"),
            "fixed_bet_amount": self.data.get("fixed_bet_amount", 1.0),
            "bet_fraction": self.data["bet_fraction"],
            "max_live_amount": self.data.get("max_live_amount", 1.0),
            "withdraw_mode": self.data["withdraw_mode"],
            "max_consecutive_losses": self.data["max_consecutive_losses"],
            "cooldown_seconds": self.data["cooldown_seconds"],
            "initial_capital": self.data["initial_capital"],
            "strategies": self.strategies,
            "active_strategy": self.active_strategy,
        }
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def switch_strategy(self, sid):
        sid = str(sid)
        if sid in self.strategies:
            self.active_strategy = sid
            p = self.strategies[sid]["params"]
            for k, v in p.items():
                self.data[k] = v
            self.save()
            return True
        return False

    def update_strategy(self, sid, params=None):
        sid = str(sid)
        if sid in self.strategies:
            if params:
                self.strategies[sid]["params"].update(params)
            if sid == self.active_strategy:
                p = self.strategies[sid]["params"]
                for k, v in p.items():
                    self.data[k] = v
            self.save()
            return True
        return False

    def load_state(self):
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_state(self, state):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
