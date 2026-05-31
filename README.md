# 🎯 Polymarket BTC 5M Auto-Trading System

> Automated trading system for Polymarket BTC 5-minute prediction markets

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[English](#features) | [中文](#功能特性)

---

## Features

- 📊 **Real-time Data Collection** — WebSocket-based BTC price and market data streaming
- 🤖 **Automated Trading** — Strategy engine with configurable entry/exit rules
- 📈 **Backtesting** — Historical performance analysis with detailed metrics
- 🖥️ **Web Dashboard** — Real-time monitoring and control interface
- 🔒 **Risk Management** — Position sizing, stop-loss, and exposure limits

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Collector   │────▶│   Trader    │────▶│   CLOB API  │
│  (WebSocket) │     │  (Strategy) │     │ (Polymarket)│
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                    ┌──────▼──────┐
                    │    WebUI    │
                    │ (Dashboard) │
                    └─────────────┘
```

## Components

| Module | Description |
|--------|-------------|
| `btc5m-collector/` | Real-time data collection (BTC price, market events, orderbook) |
| `btc5m-trader/` | Trading strategy engine with live/sim modes |
| `btc5m-webui/` | Web-based monitoring dashboard |
| `docs/` | Architecture documentation and analysis reports |
| `windows/` | Windows-specific deployment scripts |
| `runtime/` | Runtime configuration and state management |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+ (for WebUI)
- Polymarket API key

### Installation

```bash
# Clone the repository
git clone https://github.com/yyq7903/auto-trading.git
cd auto-trading

# Install Python dependencies
pip install -r requirements.txt

# Copy and configure environment
cp btc5m-trader/.env.example btc5m-trader/.env
# Edit .env with your API keys

# Start the collector
python btc5m-collector/collect.py

# Start the trader (simulation mode first!)
python btc5m-trader/sim/trader.py

# Start the WebUI (optional)
cd btc5m-webui && npm install && npm run dev
```

### Configuration

Edit `btc5m-trader/config.json`:

```json
{
  "entry_threshold": 0.75,
  "min_gap": 10,
  "max_position": 100,
  "risk_per_trade": 0.02
}
```

## Strategy

The system trades Polymarket's BTC 5-minute prediction markets based on:

1. **Price Gap Analysis** — Measures deviation from Chainlink oracle price
2. **Timing Window** — Enters between T-25s and T-5s before settlement
3. **Direction Logic** — Up if gap ≥ 0, Down if gap < 0
4. **Risk Checks** — Validates balance, position size, and exposure limits

## Performance

Backtesting results on historical data:

| Metric | Value |
|--------|-------|
| Markets Analyzed | 133 |
| Signal Accuracy | 55-65% |
| Avg Trade Duration | ~5 min |
| Risk per Trade | 2% of bankroll |

## Tech Stack

- **Python** — Core trading logic and data collection
- **WebSocket** — Real-time market data streaming
- **Polymarket CLOB API** — Order execution
- **Chainlink Oracle** — Price reference
- **React/Vite** — Web dashboard

## Contributing

Contributions welcome! Please read the [contributing guidelines](CONTRIBUTING.md) first.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Disclaimer

⚠️ **This is experimental software for educational purposes.**

- Trading involves risk of loss
- Past performance does not guarantee future results
- Use at your own risk
- Never trade with money you cannot afford to lose

## License

MIT License — see [LICENSE](LICENSE) for details.

---

**Built with ❤️ for the Polymarket community**
