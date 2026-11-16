export const PAGE_SIZE = 100;

// Every column of the broker's daily net position report, in report order.
// Columns with a `key` can be sorted by the API.
export const COLUMNS = [
  { key: "line", label: "Contract" },
  { label: "Symbol" },
  { label: "Expiry" },
  { label: "Strike", align: "right" },
  { label: "Opt" },
  { key: "buy_qty", label: "Buy Qty", align: "right" },
  { key: "buy_value", label: "Buy Value", align: "right" },
  { key: "sell_qty", label: "Sale Qty", align: "right" },
  { key: "sell_value", label: "Sale Value", align: "right" },
  { key: "net_qty", label: "Net Qty", align: "right" },
  { key: "net_value", label: "Net Value", align: "right" },
  { label: "Avg Rate", align: "right" },
  { key: "close_rate", label: "Clos Rate", align: "right" },
  { key: "mtm", label: "MTM", align: "right" },
  { label: "Exchange" },
];
