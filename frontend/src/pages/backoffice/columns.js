export const PAGE_SIZE = 50;

export const DAILY_COLUMNS = [
  { key: "date", label: "Date" },
  { key: "buy_value", label: "Buy Value", align: "right" },
  { key: "sell_value", label: "Sell Value", align: "right" },
  { key: "net_value", label: "Net Value", align: "right" },
  { key: "realized_pnl", label: "Realized P&L", align: "right" },
  { key: "unrealized_pnl", label: "Unrealized P&L (EOD)", align: "right" },
  { key: "broker_mtm", label: "MTM (Realised + Unrealised)", align: "right" },
  { key: "matched_trades", label: "Squared-off Contracts", align: "right" },
];

export const MONTHLY_COLUMNS = [
  { key: "month", label: "Month" },
  { key: "buy_value", label: "Buy Value", align: "right" },
  { key: "sell_value", label: "Sell Value", align: "right" },
  { key: "opening_value", label: "C/F Opening", align: "right" },
  { key: "net_value", label: "Net Value", align: "right" },
  { key: "realized_pnl", label: "Realized P&L", align: "right" },
  { key: "unrealized_pnl", label: "Unrealized (Month End)", align: "right" },
  { key: "broker_mtm", label: "MTM (Realised + Unrealised)", align: "right" },
  { key: "mtm_pnl", label: "Change in month", align: "right" },
  { key: "trading_days", label: "Trading Days", align: "right" },
];

export const POSITION_COLUMNS = [
  { key: "symbol", label: "Trading Symbol" },
  { key: "side", label: "Side" },
  { key: "open_qty", label: "Open Qty", align: "right" },
  { key: "avg_price", label: "Avg Open Price", align: "right" },
  { key: "ltp", label: "LTP", align: "right" },
  { label: "LTP Source" },
  { key: "unrealized_pnl", label: "Unrealized P&L", align: "right" },
];
