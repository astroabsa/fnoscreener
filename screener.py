# screener.py — Core FnO RSI/SMA Screener Logic (FIXED)

import requests
import gzip
import json
import pandas as pd
from datetime import datetime, timedelta
import time
import config

def _get_headers():
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {config.UPSTOX_ACCESS_TOKEN}"
    }

# ─────────────────────────────────────────────────────────
# INSTRUMENTS
# Strategy:
#   1. Try complete.json.gz (no auth needed, public)
#   2. Fallback to hardcoded SEBI FnO list
# ─────────────────────────────────────────────────────────

# Hardcoded SEBI-approved FnO stocks (as of May 2026)
# Used as fallback if instrument file download fails
HARDCODED_FNO_SYMBOLS = [
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","SBIN","BHARTIARTL",
    "KOTAKBANK","ITC","LT","AXISBANK","ASIANPAINT","MARUTI","TITAN","BAJFINANCE",
    "SUNPHARMA","ULTRACEMCO","WIPRO","ONGC","POWERGRID","NTPC","TECHM","HCLTECH",
    "TATAMOTORS","TATASTEEL","JSWSTEEL","ADANIENT","ADANIPORTS","ADANIGREEN",
    "BAJAJFINSV","BRITANNIA","CIPLA","DRREDDY","DIVISLAB","EICHERMOT","GRASIM",
    "HEROMOTOCO","HINDALCO","INDUSINDBK","NESTLEIND","SBILIFE","BAJAJ-AUTO",
    "BPCL","COALINDIA","HDFCLIFE","M&M","TATACONSUM","UPL","VEDL",
    "APOLLOHOSP","DMART","NYKAA","PAYTM","ZOMATO","IRCTC","HAL","BEL",
    "PIDILITIND","SIEMENS","HAVELLS","VOLTAS","MUTHOOTFIN","BANKBARODA",
    "CANBK","PNB","FEDERALBNK","IDFCFIRSTB","AUBANK","RBLBANK","BANDHANBNK",
    "MOTHERSON","BALKRISIND","APOLLOTYRE","MRF","EXIDEIND","AMBUJACEM",
    "ACC","SHREECEM","RAMCOCEM","JKCEMENT","ASTRAL","POLYCAB","KEI",
    "ABCAPITAL","MFSL","CHOLAFIN","LICHSGFIN","MANAPPURAM","RECLTD","PFC",
    "IRFC","HUDCO","NHPC","SJVN","TATAPOWER","ADANITRANS","TORNTPOWER",
    "CESC","JPPOWER","SUZLON","INOXWIND","AARTIIND","DEEPAKNTR","PIDILITIND",
    "SRF","ATUL","NAVINFLUOR","FLUOROCHEM","ALKYLAMINE","TATACHEM","GNFC",
    "CHAMBLFERT","COROMANDEL","UBL","MCDOWELL-N","RADICO","UNITDSPR",
    "ZYDUSLIFE","TORNTPHARM","AUROPHARMA","LUPIN","BIOCON","ALKEM","GLAND",
    "LALPATHLAB","METROPOLIS","MAXHEALTH","FORTIS","MEDANTA","RAINBOW",
    "INDHOTEL","LEMONTREE","CHALET","DEVYANI","JUBLFOOD","WESTLIFE","SAPPHIRE",
    "NAUKRI","PERSISTENT","LTIM","COFORGE","MPHASIS","KPITTECH","TATAELXSI",
    "MASTEK","NIITTECH","RATEGAIN","REDINGTON","WIPRO","OFSS","INFY","TCS",
    "ZEEL","SUNTV","PVRINOX","INOXLEISUR","NAZARA","NETWORK18","TV18BRDCST",
    "CONCOR","BLUEDART","GATI","VRL","MAHLOG","LINDEINDIA","CLEAN","CARBORUNIV",
    "GRINDWELL","CUMMINSIND","THERMAX","BHEL","ABB","APLAPOLLO","WELCORP",
    "RAMASTEEL","JINDALSAW","NATIONALUM","HINDZINC","MOIL","GMRINFRA","IRB",
    "KNRCON","PNCINFRA","HG INFRA","NBCC","NCC","AHLUWALIA","PSP","CAPACITE",
    "SOBHA","BRIGADE","GODREJPROP","PRESTIGE","PHOENIXLTD","DLF","OBEROIRLTY",
    "MAHINDCIE","SUNDARMFIN","TIINDIA","SCHAEFFLER","SKF","TIMKEN","FINEORG",
    "HLEG","POWERINDIA","EMAMILTD","MARICO","GODREJCP","DABUR","COLPAL","VBL",
    "TATACOMM","INDIAMART","JUSTDIAL","POLICYBZR","CARTRADE","EASEMYTRIP"
]

def _symbol_to_instrument_key(symbol: str) -> str:
    """Best-effort conversion: most NSE EQ stocks use ISIN-based keys.
    We use the Upstox instrument search API to resolve the key."""
    url = f"https://api.upstox.com/v2/instruments/search?query={symbol}&segment=NSE_EQ"
    try:
        resp = requests.get(url, headers=_get_headers(), timeout=8)
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            for item in data:
                if (item.get("trading_symbol") == symbol and
                        item.get("instrument_type") == "EQ" and
                        item.get("segment") == "NSE_EQ"):
                    return item.get("instrument_key", "")
    except Exception:
        pass
    return ""


def get_fno_eq_instrument_keys() -> dict:
    """
    Returns { 'RELIANCE': 'NSE_EQ|INE002A01018', ... } for FnO equity stocks.

    Strategy:
      1. Try downloading complete.json.gz (public, no auth)
      2. If that fails, try NSE_FO.json.gz
      3. If both fail, use hardcoded symbol list + resolve via Search API
    """
    candidate_urls = [
        "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz",
        "https://assets.upstox.com/market-quote/instruments/exchange/NSE_FO.json.gz",
    ]

    instruments = None
    for url in candidate_urls:
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                raw = resp.content
                # Try gzip decompression
                try:
                    decompressed = gzip.decompress(raw)
                    instruments = json.loads(decompressed.decode("utf-8"))
                except Exception:
                    # Maybe it's plain JSON
                    instruments = resp.json()
                break
        except Exception:
            continue

    if instruments:
        # Parse the instrument list to find FnO equities
        fno_symbols = {}
        for inst in instruments:
            if (inst.get("instrument_type") == "FUT" and
                    inst.get("underlying_type") == "EQUITY" and
                    inst.get("segment") == "NSE_FO"):
                symbol = inst.get("underlying_symbol")
                u_key  = inst.get("underlying_key")
                if symbol and u_key and symbol not in fno_symbols:
                    fno_symbols[symbol] = u_key
        if fno_symbols:
            return fno_symbols

    # ── FALLBACK: hardcoded list + Search API resolution ──────────────
    # Use Upstox /v2/instruments/search to resolve instrument_key per symbol
    fno_symbols = {}
    for symbol in HARDCODED_FNO_SYMBOLS:
        key = _symbol_to_instrument_key(symbol)
        if key:
            fno_symbols[symbol] = key
        time.sleep(0.2)   # gentle rate limit on search API

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

    resp = requests.get(url, headers=_get_headers(), timeout=10)
    if resp.status_code != 200:
        return pd.DataFrame()

    try:
        candles = resp.json().get("data", {}).get("candles", [])
    except Exception:
        return pd.DataFrame()

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
    """Returns (signal, rsi_val, sma_val) — signal is 'CROSSOVER', 'CROSSUNDER', or None."""
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

    rsi_val = round(float(curr["rsi"]), 2)
    sma_val = round(float(curr["rsi_sma"]), 2)

    if not prev_above and curr_above:
        return "CROSSOVER", rsi_val, sma_val
    elif prev_above and not curr_above:
        return "CROSSUNDER", rsi_val, sma_val
    return None, rsi_val, sma_val


# ─────────────────────────────────────────────────────────
# MAIN SCAN
# ─────────────────────────────────────────────────────────
def run_scan(progress_callback=None) -> list:
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
                    "Close":         round(float(last["close"]), 2),
                    "LastCandle":    last["timestamp"].strftime("%Y-%m-%d %H:%M"),
                    "ScannedAt":     datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
        except Exception:
            pass

        if i % 3 == 0:
            time.sleep(config.RATE_LIMIT_SLEEP)

    return results
