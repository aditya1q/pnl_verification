// "NIFTY03NOVOPT 23300 PE"; futures have no strike or option type.
export function contractLabel(row) {
  const strike = row.strike && Number(row.strike) !== 0 ? ` ${row.strike}` : "";
  const option = row.option_type && row.option_type !== "FX" ? ` ${row.option_type}` : "";
  return `${row.symbol ?? "—"}${strike}${option}`;
}

export function positionKey(row) {
  return [row.exchange, row.symbol, row.expiry, row.strike, row.option_type].join("|");
}
