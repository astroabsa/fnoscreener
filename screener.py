# screener.py — Core FnO RSI/SMA Screener Logic

import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import config

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Authorization": f"Bearer {config.UPSTOX_ACCESS_TOKEN}"
}


# ─────────────────────────────────────────────────────────
# INSTRUMENTS
# ─────────────────────────────────────────────────────────
def get_fno_eq_instrument_keys() -> dict:
    """Returns { 'RELIANCE': 'NSE_EQ|INE002A01018', ... } for all FnO equities."""
    url  = "https://assets.upstox.com/market-quote/instruments/exchange/NSE_FO.json.gz"
    resp = requests.get(url, timeout=30)
    instruments = resp.json()

    fno_symbols = {}
    for inst in instruments:
        if inst.get("instrument_type") == "FUT" and inst.get("underlying_type") == "EQUITY":
            symbol = inst.get("underlying_symbol")
            u_key  = inst.get("underlying_key")
            if symbol and u_key and symbol not in fno_symbols:
                fno_symbols[symbol] = u_key

    return fno_symbols


# ─────────────────────────────────────────────────────────
# CANDLE DATA
# ─────────────────────────────────────────────────────────
def fetch_4h_candles(instrument_key: str) -> pd.DataFrame:
    to_date   = datetime.today().strftime("%Y-%m-%d")
    from_date = (datetime.today() - timedelta(days=config.DAYS_BACK)).strftime("%Y-%m-%d")
    encoded   = requests.utils.quote(instrument_key, safe="")

    url = (
        f"https://api.upstox.com/v3/historical-candle/"
        f"{encoded}/{config.CANDLE_UNIT}/{config.CANDLE_INTERVAL}/{to_date}/{from_date}"
    )

    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code != 200:
        return pd.DataFrame()

    candles = resp.json().get("data", {}).get("candles", [])
    if not candles:
        return pd.DataFrame()

    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


# ─────────────────────────────────────────────────────────
# INDICATORS
# ─────────────────────────────────────────────────────────
def calculate_rsi(series: pd.Series, period: int) -> pd.Series:
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs       = avg_gain / avg_loss.replace(0, float("inf"))
    return 100 - (100 / (1 + rs))


def detect_crossover(df: pd.DataFrame):
    """Returns 'CROSSOVER', 'CROSSUNDER', or None."""
    min_candles = config.RSI_PERIOD + config.SMA_PERIOD + 5
    if len(df) < min_candles:
        return None, None, None

    df = df.copy()
    df["rsi"]     = calculate_rsi(df["close"], config.RSI_PERIOD)
    df["rsi_sma"] = df["rsi"].rolling(config.SMA_PERIOD).mean()
    df.dropna(inplace=True)

    if len(df) < 2:
        return None, None, None

    prev, curr = df.iloc[-2], df.iloc[-1]
    prev_above = prev["rsi"] > prev["rsi_sma"]
    curr_above = curr["rsi"] > curr["rsi_sma"]

    rsi_val = round(curr["rsi"], 2)
    sma_val = round(curr["rsi_sma"], 2)

    if not prev_above and curr_above:
        return "CROSSOVER", rsi_val, sma_val
    elif prev_above and not curr_above:
        return "CROSSUNDER", rsi_val, sma_val
    return None, rsi_val, sma_val


# ─────────────────────────────────────────────────────────
# MAIN SCAN
# ─────────────────────────────────────────────────────────
def run_scan(progress_callback=None) -> list[dict]:
    """
    Runs full FnO scan. Calls progress_callback(i, total, symbol) if provided.
    Returns list of result dicts (only stocks with crossover signals).
    """
    fno_stocks = get_fno_eq_instrument_keys()
    total      = len(fno_stocks)
    results    = []

    for i, (symbol, instrument_key) in enumerate(fno_stocks.items(), 1):
        if progress_callback:
            progress_callback(i, total, symbol)
        try:
            df = fetch_4h_candles(instrument_key)
            if df.empty:
                continue

            signal, rsi_val, sma_val = detect_crossover(df)

            if signal:
                last = df.iloc[-1]
                results.append({
                    "Symbol":        symbol,
                    "InstrumentKey": instrument_key,
                    "Signal":        signal,
                    "RSI(10)":       rsi_val,
                    "SMA14(RSI10)":  sma_val,
                    "Close":         round(last["close"], 2),
                    "LastCandle":    last["timestamp"].strftime("%Y-%m-%d %H:%M"),
                    "ScannedAt":     datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
        except Exception:
            pass

        if i % 3 == 0:
            time.sleep(config.RATE_LIMIT_SLEEP)

    return results
