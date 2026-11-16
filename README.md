# Net Position P&L App

A small full-stack app for the NSE / BSE F&O account. Each trading day you upload the broker's daily **net position** report. The app stores every column of it in MongoDB, shows it day by day, and calculates realized and unrealized P&L by day and by month, starting from the Carry Forward (C/F).

Trade files are no longer used. The trade upload, the trade view and the FIFO engine were removed on 5 Nov 2026. The last stored trades are backed up in `backend/data/backups/`.

## Stack
- Backend: FastAPI + PyMongo
- Frontend: React + Vite
- Database: MongoDB Community Server
- Frontend: React + Tailwind CSS v4 + shadcn/ui. `src/components/ui/` = shadcn components (add more with `npx shadcn@latest add <name>`), `src/components/common/` = shared app components, `src/pages/` = one folder per page; theme colours in `src/styles/index.css`. Imports use the `@/` alias for `src/`.

## 1. Start MongoDB
Install MongoDB Community Server and start the MongoDB Server service. MongoDB Compass is optional.

Default URI: `mongodb://localhost:27017/`

## 2. Backend setup

Open a terminal in `backend`:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8002
```

Backend health: http://localhost:8002/api/health  
API docs: http://localhost:8002/docs

## 3. Frontend setup

Open a second terminal in `frontend`:

```powershell
npm install
npm run dev
```

Open the URL printed by Vite, normally http://localhost:5173.

## 4. Daily use
1. Open **Net Position** in the top bar.
2. Click **Upload net position** and choose the day's report: `NETPOSS<ddmmyyyy>_FO_B-117.csv`, `.xls`, or the `.txt` net position. The date comes from the file. NIFTY rows are stored as NSE and SENSEX/BANKEX rows as BSE.
3. Days with a report are highlighted in the date strip. Pick a day and an exchange to see every column of that day's report: Contract, Symbol, Expiry, Strike, Opt, Buy/Sale Qty and Value, Net Qty, Net Value, Avg Rate, Clos Rate, MTM and Exchange. A summary line shows the day's totals.
4. **Backoffice P&L** shows the day-wise and month-wise P&L, and the open positions.

What the import does:
- It checks that each row's Buy − Sale equals its Net Qty and Net Value, and that the rows add up to the report's own totals. No contract may appear twice, and every row needs a Close Rate.
- It refuses a day on or before the C/F date.
- Re-uploading a day replaces it, so a day is never counted twice.
- After importing, it lists weekdays since the previous report that have no report (missing, or a holiday).

## MongoDB collections
Database: `trade_ingestion`
- `carry_forward`: opening positions from the C/F report (Net Qty at Close Rate).
- `net_positions`: one document per contract and day, `_id` `<date>|<exchange>|<symbol>|<expiry>|<strike>|<opt>`. It holds every report column (`buy_qty`, `buy_value`, `sell_qty`, `sell_value`, `net_qty`, `net_value`, `avg_rate`, `close_rate`, `mtm`, `report_exchange`, `group`) plus `trade_date`, `exchange`, `client`, `source_file` and `source_line`.
- `market_prices`: the price used for unrealized P&L per contract and date. Each day's Close Rate is stored as `BROKER_CLOSE`; a manual LTP set on the Open positions tab is stored as `MANUAL`.

## P&L (broker method, account level)
The calculation is in `backend/app/broker_pnl.py` and `backend/app/backoffice.py`. All terminals are pooled per contract; there is no client-wise P&L.

| Figure | Calculation |
|---|---|
| Buy Value / Sell Value | The day's Buy / Sale Value from the net position report |
| C/F Opening | Carry Forward positions at Close Rate (long counts as bought value, short as sold value). Reported separately. |
| Net Value | Sell Value − Buy Value, as in the broker report. Cash flow, not P&L. |
| Realized P&L | Per contract per day: open positions are a FIFO queue of day-lots (each day's leftover buys or sells is one lot at that day's average price). The day's opposite side closes the oldest lots first at the day's average opposite price, the rest of the day matches at average price, and the leftover becomes a new lot. On expiry day, anything still open is settled at the bhavcopy settlement value and realized. The C/F is split into FIFO lots in `cf_lots`: the position held before the C/F date, plus what that date added at its average price. The split is built once from the C/F date's trades with `scripts/build_cf_lots.py`, and each contract's lots must add up to the C/F qty and the broker cost. With this, the app matched the broker's 2 Nov report on all 275 contracts, both realised (44,43,272.85) and unrealised (−6,58,204.64). |
| Unrealized P&L | Open qty at the end of the as-of date at average cost, marked to that day's Close Rate |
| Day / Month / Total P&L (MTM) | Realized + change in unrealized over the day / month / period |

- **Carry Forward (month-to-month cycle):** import the broker's *Clientwise Net Position* report (e.g. `backend/data/carry_forward/NFO_NETPOSITION_30102026.txt`) with **Import C/F file** on the Backoffice page. Each non-zero Net Qty becomes an opening position at the Close Rate. Re-importing replaces the previous C/F. Later months need no new C/F: positions carry forward automatically.
- **Broker P&L as on the C/F date (cumulative P&L):** import the broker's P&L report for the C/F date (e.g. `backend/data/carry_forward/MOP117_30-10-2026.csv`) with **Import C/F P&L file** (`POST /api/backoffice/opening-pnl`). It's stored in `opening_pnl` (one row per contract, every column) and `opening_pnl_summary` (TOTALS and charges).
  - Each row must add up: Realised P&L = Sell − Buy, Close Value = Qty × Close Rate, MTM = Realised + Unrealised P&L With CloseRate. The rows must also match the TOTALS row.
  - Its open positions must be exactly the C/F: the same contracts, Net Qty and Close Rate.
  - The C/F positions are then carried at the broker's **original average cost** (Unrealised Buy Value for a long, Unrealised Sell Value for a short) instead of the C/F Close Rate. Realized and unrealized are measured the broker's way.
  - **Cumulative P&L** = the report's Realised P&L + realized since the C/F + unrealized now (at original cost).
  - Day and period MTM don't change. Day MTM = realized + unrealized − the previous close's unrealized, and the C/F date's unrealized is the report's Unrealised P&L With CloseRate. Charges are shown but not deducted.
- **Current cycle:** the C/F is as of 30 Oct 2026, and the first net position is 2 Nov 2026. Broker P&L as on 30 Oct: realised −22,71,392.55, unrealised 15,53,921.46, MTM −7,17,471.09 (charges −4,05,827.29).
- **LTP:** the latest Close Rate up to the as-of date. A manual LTP overrides it, and **Reset** brings the Close Rate back. A contract that didn't trade on a day isn't in that day's report, so it keeps its last price (or the C/F Close Rate) until you set an LTP.
- **API:**
  - `GET /api/net-positions?exchange=&trade_date=&search=&sort=&order=`
  - `GET /api/net-positions/days`
  - `POST /api/net-positions` (upload)
  - `GET /api/backoffice/{options,summary,daily,monthly,positions,carry-forward,closing-rates}`
  - `POST /api/backoffice/carry-forward`
  - `PUT` and `DELETE /api/backoffice/ltp`

**Broker P&L check (calibration):** the C/F lots before the C/F date aren't in any file, so when an old C/F position is partly closed, the broker may close a pre-C/F lot at a different cost. Quantities and totals still match. Uploading the broker's daily "Realised & Unrealised" report with **Check with broker P&L** (`POST /api/backoffice/broker-pnl`, `.XLS` or `.csv`, applied oldest day first) splits off the C/F part closed that day at the broker's cost. The difference moves to the rest of that lot, so the C/F total is unchanged (`app/calibration.py`). With the reports for 2 to 5 Nov, all four days match the broker contract by contract. Before the first calibration, the lots were backed up to `backend/data/backups/cf_lots_before_calibration.json`.

**Bhavcopy (closing rates and expiry):** uploading a day's net position also downloads that day's NSE and BSE F&O bhavcopy (UDiFF: `BhavCopy_NSE_FO_0_0_0_<YYYYMMDD>_F_0000.csv.zip`, `BhavCopy_BSE_FO_..._F_0000.CSV`, saved in `backend/data/bhavcopy/`). You can also use `POST /api/bhavcopy/fetch?trade_date=` or upload one with `POST /api/bhavcopy`.
- Its `ClsPric` equals the broker's Close Rate. It's stored in `market_prices` as `BHAVCOPY` and never overwrites a net position Close Rate or a manual LTP. This means contracts that didn't trade are still marked to the day's close.
- On expiry day, `SttlmPric` is the underlying's final settlement price. Options settle at intrinsic value (CE max(0, S − K), PE max(0, K − S)), and futures at `SttlmPric`. These are stored in `settlements`.

## Tests
From `backend`:

```powershell
.venv\Scripts\python -m unittest discover -s tests
```

The Mongo tests use temporary databases and are skipped when MongoDB is not running.

## Database backup / restore (one file)
From the `backend` folder (uses `MONGODB_URI` / `MONGODB_DATABASE` from `.env`):

```powershell
# Export every collection (data + indexes) to one compressed file in data\db_dumps\
.venv\Scripts\python -m app.db_dump export

# Restore that file into the database (replaces each collection in the file)
.venv\Scripts\python -m app.db_dump import data\db_dumps\trade_ingestion_YYYYMMDD_HHMM.bson.gz
```

Options: `--out <file>` (export path), `--db <name>` / `--uri <uri>` (another database or server), `--keep` (import without replacing existing collections).
The dump contains client data: `backend/data/` is git-ignored, so share the file privately rather than through the repository.
