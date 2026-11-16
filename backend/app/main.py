from datetime import date

from bson import ObjectId
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .backoffice import DAILY_SORT_FIELDS, MONTHLY_SORT_FIELDS, POSITION_SORT_FIELDS, ReportFilters
from .carry_forward import CarryForwardError
from .closing_rates import ROW_SORT_FIELDS, ClosingRateError
from .config import CORS_ORIGINS
from .bhavcopy import BhavcopyError
from .database import MongoStore
from .opening_pnl import OpeningPnlError

app = FastAPI(title="Net Position P&L API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def make_json_safe(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {key: make_json_safe(item) for key, item in value.items() if key != "_id"}
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    return value


@app.get("/api/health")
def health():
    store = MongoStore()
    try:
        store.ping()
        return {"api": "ok", "mongodb": "connected"}
    except Exception:
        return {"api": "ok", "mongodb": "disconnected"}
    finally:
        store.close()


# --------------------------------------------------------------------------
# Daily net positions and Backoffice P&L
# --------------------------------------------------------------------------

def _optional_exchange(exchange):
    if not exchange:
        return None
    exchange = exchange.upper().strip()
    if exchange not in {"NSE", "BSE"}:
        raise HTTPException(status_code=400, detail="Only NSE and BSE are supported.")
    return exchange


def report_filters(
    exchange: str | None = Query(None, max_length=3),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    symbol: str | None = Query(None, max_length=100),
    instrument: str | None = Query(None, max_length=50),
) -> ReportFilters:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="'From' date must be on or before 'To' date.")
    return ReportFilters(
        exchange=_optional_exchange(exchange),
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        symbol=(symbol or "").strip() or None,
        instrument=(instrument or "").strip() or None,
    )


def _with_store(action, error_prefix):
    store = MongoStore()
    try:
        store.ping()
        return jsonable_encoder(action(store))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"{error_prefix}: {exc}") from exc
    finally:
        store.close()


@app.get("/api/backoffice/options")
def backoffice_options(exchange: str | None = Query(None, max_length=3)):
    exchange = _optional_exchange(exchange)
    return _with_store(
        lambda store: store.backoffice.filter_options(exchange),
        "Unable to load Backoffice filters",
    )


@app.get("/api/backoffice/summary")
def backoffice_summary(filters: ReportFilters = Depends(report_filters)):
    return _with_store(lambda store: store.backoffice.summary(filters), "Unable to load P&L summary")


@app.get("/api/backoffice/daily")
def backoffice_daily(
    filters: ReportFilters = Depends(report_filters),
    sort: str = Query("date"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=500),
    skip: int = Query(0, ge=0),
):
    if sort not in DAILY_SORT_FIELDS:
        raise HTTPException(status_code=400, detail=f"Unsupported sort field: {sort}")
    return _with_store(
        lambda store: store.backoffice.daily(filters, sort, order, limit, skip),
        "Unable to load day-wise P&L",
    )


@app.get("/api/backoffice/monthly")
def backoffice_monthly(
    filters: ReportFilters = Depends(report_filters),
    sort: str = Query("month"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=500),
    skip: int = Query(0, ge=0),
):
    if sort not in MONTHLY_SORT_FIELDS:
        raise HTTPException(status_code=400, detail=f"Unsupported sort field: {sort}")
    return _with_store(
        lambda store: store.backoffice.monthly(filters, sort, order, limit, skip),
        "Unable to load month-wise P&L",
    )


@app.get("/api/backoffice/carry-forward")
def carry_forward_status():
    return _with_store(lambda store: store.backoffice.carry_forward.status(), "Unable to read Carry Forward")


@app.post("/api/backoffice/carry-forward")
async def carry_forward_import(file: UploadFile = File(...)):
    """Import a broker net position report as the Carry Forward (replaces the previous C/F)."""
    if not file.filename or not file.filename.lower().endswith((".txt", ".csv", ".prn")):
        raise HTTPException(status_code=400, detail="Upload the net position report (.txt).")
    try:
        text = (await file.read()).decode("utf-8", errors="replace")
    finally:
        await file.close()

    def action(store):
        store.indexes()
        try:
            return store.backoffice.carry_forward.import_report(text, file.filename)
        except CarryForwardError as exc:
            raise HTTPException(status_code=422, detail=f"Carry Forward not imported: {exc}") from exc

    return _with_store(action, "Carry Forward import failed")


@app.get("/api/backoffice/opening-pnl")
def opening_pnl_status():
    return _with_store(lambda store: make_json_safe(store.backoffice.opening_pnl.summary() or {}),
                       "Unable to read the C/F P&L report")


@app.post("/api/backoffice/opening-pnl")
async def opening_pnl_import(file: UploadFile = File(...)):
    """Import the broker's P&L report as on the C/F date (realised / unrealised at original cost)."""
    if not file.filename or not file.filename.lower().endswith((".csv", ".xls")):
        raise HTTPException(status_code=400, detail="Upload the broker's P&L report (.csv or .XLS), e.g. MOP117_30-10-2026.csv.")
    try:
        content = await file.read()
    finally:
        await file.close()

    def action(store):
        try:
            return make_json_safe(store.backoffice.opening_pnl.import_report(content, file.filename))
        except OpeningPnlError as exc:
            raise HTTPException(status_code=422, detail=f"P&L report not imported: {exc}") from exc

    return _with_store(action, "P&L report import failed")


@app.get("/api/bhavcopy")
def bhavcopy_status():
    return _with_store(lambda store: make_json_safe(store.backoffice.bhavcopy.status()), "Unable to read bhavcopy status")


@app.post("/api/bhavcopy/fetch")
def bhavcopy_fetch(trade_date: date = Query(...)):
    """Download the NSE and BSE F&O bhavcopy of a day: closing rates and expiry settlement prices."""
    def action(store):
        store.indexes()
        return make_json_safe(store.backoffice.bhavcopy.fetch(trade_date.isoformat()))
    return _with_store(action, "Bhavcopy download failed")


@app.post("/api/bhavcopy")
async def bhavcopy_upload(file: UploadFile = File(...), exchange: str | None = Query(None, max_length=3)):
    """Upload a UDiFF F&O bhavcopy (.csv or .zip) when it cannot be downloaded."""
    try:
        content = await file.read()
    finally:
        await file.close()

    def action(store):
        store.indexes()
        try:
            return make_json_safe(store.backoffice.bhavcopy.import_file(content, file.filename, exchange))
        except BhavcopyError as exc:
            raise HTTPException(status_code=422, detail=f"Bhavcopy not imported: {exc}") from exc
    return _with_store(action, "Bhavcopy import failed")


@app.post("/api/backoffice/broker-pnl")
async def broker_pnl_calibrate(file: UploadFile = File(...)):
    """Broker's daily "Realised & Unrealised" report (.XLS or .csv) for a day after the C/F:
    corrects the cost of the pre-C/F lots closed that day so realised matches the broker."""
    if not file.filename or not file.filename.lower().endswith((".xls", ".csv")):
        raise HTTPException(status_code=400, detail="Upload the broker P&L report (.XLS or .csv), e.g. MOP117_04-11-2026.XLS.")
    try:
        content = await file.read()
    finally:
        await file.close()

    def action(store):
        from .calibration import Calibrator
        try:
            return make_json_safe(Calibrator(store.backoffice).calibrate(content, file.filename))
        except OpeningPnlError as exc:
            raise HTTPException(status_code=422, detail=f"Broker P&L not applied: {exc}") from exc

    return _with_store(action, "Broker P&L calibration failed")


@app.get("/api/net-positions")
def net_positions_day(
    exchange: str = Query(..., min_length=3, max_length=3),
    trade_date: date = Query(...),
    search: str = Query("", max_length=100),
    sort: str = Query("line"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
):
    """The daily net position rows of one exchange and day (every report column)."""
    exchange = _optional_exchange(exchange)
    if sort not in ROW_SORT_FIELDS:
        raise HTTPException(status_code=400, detail=f"Unsupported sort field: {sort}")
    return _with_store(
        lambda store: make_json_safe(store.backoffice.closing_rates.rows(
            exchange, trade_date.isoformat(), search, sort, order, limit, skip)),
        "Unable to load net positions",
    )


@app.get("/api/net-positions/days")
def net_position_days():
    """Every imported day per exchange, newest first."""
    return _with_store(lambda store: store.backoffice.closing_rates.status(), "Unable to read net positions")


@app.post("/api/net-positions")
async def net_position_import(file: UploadFile = File(...)):
    return await closing_rates_import(file)


@app.get("/api/backoffice/closing-rates")
def closing_rates_status():
    return _with_store(lambda store: store.backoffice.closing_rates.status(), "Unable to read closing rates")


@app.post("/api/backoffice/closing-rates")
async def closing_rates_import(file: UploadFile = File(...)):
    """Import the broker's daily net position report (one day): the P&L input and its Close Rates."""
    if not file.filename or not file.filename.lower().endswith((".xls", ".csv", ".txt", ".prn")):
        raise HTTPException(status_code=400, detail="Upload the broker's daily net position report (.xls, .csv or .txt).")
    try:
        content = await file.read()
    finally:
        await file.close()

    def action(store):
        store.indexes()
        try:
            result = store.backoffice.closing_rates.import_report(content, file.filename)
        except ClosingRateError as exc:
            raise HTTPException(status_code=422, detail=f"Net position not imported: {exc}") from exc
        # Closing rates for contracts not traded that day, and expiry settlements (best effort).
        try:
            result["bhavcopy"] = make_json_safe(store.backoffice.bhavcopy.fetch(result["date"]))
        except Exception as exc:  # pragma: no cover - network dependent
            result["bhavcopy"] = {"date": result["date"], "imported": [], "errors": {"ALL": str(exc)}}
        return result

    return _with_store(action, "Net position import failed")


@app.get("/api/backoffice/positions")
def backoffice_positions(
    filters: ReportFilters = Depends(report_filters),
    as_of: date | None = Query(None),
    sort: str = Query("unrealized_pnl"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=500),
    skip: int = Query(0, ge=0),
):
    """Open positions marked to LTP as of a date (default: 'To' date, else latest)."""
    if sort not in POSITION_SORT_FIELDS:
        raise HTTPException(status_code=400, detail=f"Unsupported sort field: {sort}")
    return _with_store(
        lambda store: store.backoffice.position_rows(
            filters, as_of.isoformat() if as_of else None, sort, order, limit, skip),
        "Unable to load open positions",
    )


class LtpKey(BaseModel):
    exchange: str = Field(..., min_length=3, max_length=3)
    symbol: str = Field(..., min_length=1, max_length=100)
    expiry: str | None = Field(None, max_length=50)
    strike: float | int | None = None
    option_type: str | None = Field(None, max_length=10)
    date: date


class LtpUpdate(LtpKey):
    ltp: float = Field(..., ge=0)


def _ltp_args(body: LtpKey):
    strike = body.strike
    if isinstance(strike, float) and strike.is_integer():
        strike = int(strike)  # match how strikes are stored on net positions
    return (_optional_exchange(body.exchange), body.symbol, body.expiry, strike,
            body.option_type, body.date.isoformat())


@app.put("/api/backoffice/ltp")
def backoffice_set_ltp(body: LtpUpdate):
    """Store a manual LTP for one contract and date (overrides the Close Rate)."""
    args = _ltp_args(body)
    return _with_store(lambda store: store.backoffice.set_ltp(*args, body.ltp), "Unable to save LTP")


@app.delete("/api/backoffice/ltp")
def backoffice_clear_ltp(body: LtpKey):
    args = _ltp_args(body)
    return _with_store(lambda store: store.backoffice.clear_ltp(*args), "Unable to clear LTP")
