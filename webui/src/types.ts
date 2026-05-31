export interface StrategySlot {
  name: string;
  entry: number;
  gap: number;
  prob: number;
  cool: number;
  dir: "both" | "up" | "down";
  fund: "fixed" | "amount";
  fundParam: number;
}

export interface TradeRow {
  time: string;
  dir: string;
  open: number;
  btc: number;
  settle: number | null;
  gap: number;
  settle_gap: number | string;
  winner: string;
  prob: number | string;
  amount: number | string;
  pnl: number | string;
  ret: string;
  status: "won" | "lost" | "skipped";
  skip: string;
  entry: string;
}

export interface MarketRow {
  slug: string;
  market_time: string;
  winner: string;
  final_gap: number;
  has_trade: boolean;
  trade_status: string;
  reversal: boolean;
}
