# app.py — Streamlit Dashboard

import streamlit as st
import pandas as pd
from datetime import datetime
import requests
import config
import screener

# ─────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FnO RSI Screener",
    page_icon="📈",
    layout="wide"
)

# ─────────────────────────────────────────────────────────
# TELEGRAM ALERT
# ─────────────────────────────────────────────────────────
def send_telegram_alert(results: list[dict]):
    """Sends a Telegram message summarizing all crossover signals found."""
    if not results:
        return

    crossovers  = [r for r in results if r["Signal"] == "CROSSOVER"]
    crossunders = [r for r in results if r["Signal"] == "CROSSUNDER"]

    lines = ["🔔 *FnO RSI(10) Screener Alert* — 4H Timeframe\n"]
    lines.append(f"🕐 Scanned at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST")
    lines.append(f"📊 Total Signals: {len(results)}\n")

    if crossovers:
        lines.append("🟢 *CROSSOVER (Bullish)*")
        for r in crossovers:
            lines.append(
                f"  • `{r['Symbol']}` | RSI: {r['RSI(10)']} | SMA: {r['SMA14(RSI10)']} "
                f"| Close: ₹{r['Close']} | {r['LastCandle']}"
            )

    if crossunders:
        lines.append("\n🔴 *CROSSUNDER (Bearish)*")
        for r in crossunders:
            lines.append(
                f"  • `{r['Symbol']}` | RSI: {r['RSI(10)']} | SMA: {r['SMA14(RSI10)']} "
                f"| Close: ₹{r['Close']} | {r['LastCandle']}"
            )

    message = "\n".join(lines)
    url     = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"

    try:
        resp = requests.post(url, json={
            "chat_id":    config.TELEGRAM_CHAT_ID,
            "text":       message,
            "parse_mode": "Markdown"
        }, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


# ─────────────────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────────────────
if "results"        not in st.session_state: st.session_state.results        = []
if "last_scan_time" not in st.session_state: st.session_state.last_scan_time = None
if "scan_history"   not in st.session_state: st.session_state.scan_history   = []
if "alert_sent"     not in st.session_state: st.session_state.alert_sent     = False


# ─────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────
st.title("📈 FnO RSI(10) Crossover Screener")
st.caption("Scans all NSE F&O stocks · RSI(10) vs SMA14(RSI10) · 4H Timeframe")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("RSI Period",      f"{config.RSI_PERIOD}")
with col2:
    st.metric("SMA Period",      f"{config.SMA_PERIOD}")
with col3:
    st.metric("Timeframe",       "4H")
with col4:
    last_scan = st.session_state.last_scan_time or "Never"
    st.metric("Last Scanned",    str(last_scan))

st.divider()

# ─────────────────────────────────────────────────────────
# SIDEBAR — Settings & Controls
# ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")

    st.subheader("Filter")
    show_crossover  = st.checkbox("🟢 Show Crossovers",  value=True)
    show_crossunder = st.checkbox("🔴 Show Crossunders", value=True)

    st.subheader("Telegram")
    tg_enabled = st.toggle("Enable Telegram Alerts", value=True)
    if st.button("🧪 Test Telegram Alert"):
        ok = send_telegram_alert([{
            "Symbol": "TEST", "Signal": "CROSSOVER",
            "RSI(10)": 52.3, "SMA14(RSI10)": 49.1,
            "Close": 1234.5, "LastCandle": datetime.now().strftime("%Y-%m-%d %H:%M")
        }])
        st.success("✅ Test alert sent!") if ok else st.error("❌ Failed. Check bot token & chat ID.")

    st.subheader("Auto Refresh")
    auto_refresh    = st.toggle("Enable Auto-Refresh", value=False)
    refresh_minutes = st.selectbox("Interval", [60, 120, 240, 480], index=2,
                                   format_func=lambda x: f"Every {x} min ({x//60}H)")

    st.divider()
    st.caption("📌 Token rotates daily — update `config.py` each morning.")


# ─────────────────────────────────────────────────────────
# SCAN BUTTON
# ─────────────────────────────────────────────────────────
scan_col, _ = st.columns([1, 4])
with scan_col:
    scan_clicked = st.button("🔍 Run Scan Now", type="primary", use_container_width=True)


# ─────────────────────────────────────────────────────────
# AUTO REFRESH TRIGGER
# ─────────────────────────────────────────────────────────
if auto_refresh and st.session_state.last_scan_time:
    elapsed = (datetime.now() - st.session_state.last_scan_time).seconds / 60
    if elapsed >= refresh_minutes:
        scan_clicked = True


# ─────────────────────────────────────────────────────────
# RUN SCAN
# ─────────────────────────────────────────────────────────
if scan_clicked:
    st.session_state.alert_sent = False
    progress_bar  = st.progress(0, text="Initialising scan...")
    status_text   = st.empty()

    def update_progress(i, total, symbol):
        pct = int((i / total) * 100)
        progress_bar.progress(pct, text=f"Scanning {symbol} ({i}/{total})...")
        status_text.caption(f"⏳ {symbol}")

    with st.spinner("Running FnO scan..."):
        results = screener.run_scan(progress_callback=update_progress)

    progress_bar.empty()
    status_text.empty()

    st.session_state.results        = results
    st.session_state.last_scan_time = datetime.now()

    # Append to history log
    st.session_state.scan_history.append({
        "Time":           datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Signals Found":  len(results),
        "Crossovers":     sum(1 for r in results if r["Signal"] == "CROSSOVER"),
        "Crossunders":    sum(1 for r in results if r["Signal"] == "CROSSUNDER"),
    })

    # Send Telegram only if signals found and enabled
    if results and tg_enabled and not st.session_state.alert_sent:
        ok = send_telegram_alert(results)
        st.session_state.alert_sent = True
        if ok:
            st.toast(f"📲 Telegram alert sent for {len(results)} signal(s)!", icon="✅")
        else:
            st.toast("⚠️ Telegram alert failed to send.", icon="❌")

    if results:
        st.success(f"✅ Scan complete — {len(results)} signal(s) found!")
    else:
        st.info("ℹ️ Scan complete — No crossover signals on this scan.")


# ─────────────────────────────────────────────────────────
# RESULTS TABLE
# ─────────────────────────────────────────────────────────
results = st.session_state.results

if results:
    df = pd.DataFrame(results)

    # Apply sidebar filters
    if not show_crossover:
        df = df[df["Signal"] != "CROSSOVER"]
    if not show_crossunder:
        df = df[df["Signal"] != "CROSSUNDER"]

    st.subheader(f"📋 Signals Found — {len(df)} stock(s)")

    # Tabs: Crossover | Crossunder | All
    tab1, tab2, tab3 = st.tabs(["🟢 Crossovers", "🔴 Crossunders", "📊 All Signals"])

    def style_signal(val):
        color = "#1a7a1a" if val == "CROSSOVER" else "#8b0000"
        bg    = "#d4edda"  if val == "CROSSOVER" else "#f8d7da"
        return f"background-color: {bg}; color: {color}; font-weight: bold;"

    display_cols = ["Symbol", "Signal", "RSI(10)", "SMA14(RSI10)", "Close", "LastCandle"]

    with tab1:
        dfco = df[df["Signal"] == "CROSSOVER"][display_cols]
        if dfco.empty:
            st.info("No Crossover signals.")
        else:
            st.dataframe(
                dfco.style.applymap(style_signal, subset=["Signal"]),
                use_container_width=True, hide_index=True
            )

    with tab2:
        dfcu = df[df["Signal"] == "CROSSUNDER"][display_cols]
        if dfcu.empty:
            st.info("No Crossunder signals.")
        else:
            st.dataframe(
                dfcu.style.applymap(style_signal, subset=["Signal"]),
                use_container_width=True, hide_index=True
            )

    with tab3:
        st.dataframe(
            df[display_cols].style.applymap(style_signal, subset=["Signal"]),
            use_container_width=True, hide_index=True
        )

    # Download button
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download Results CSV",
        data=csv,
        file_name=f"fno_rsi_signals_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv"
    )

elif st.session_state.last_scan_time:
    st.info("ℹ️ No crossover signals found in the last scan. Telegram alert was NOT sent.")

else:
    st.markdown("""
    ### 👆 Click **Run Scan Now** to start
    The screener will:
    - Load all ~200 FnO eligible NSE stocks
    - Fetch 4H historical candles (90 days)
    - Compute RSI(10) and its SMA(14)
    - Filter stocks where a crossover/crossunder just occurred
    - Send a **Telegram alert only if signals are found**
    """)


# ─────────────────────────────────────────────────────────
# SCAN HISTORY LOG
# ─────────────────────────────────────────────────────────
if st.session_state.scan_history:
    st.divider()
    st.subheader("🕐 Scan History (This Session)")
    hist_df = pd.DataFrame(st.session_state.scan_history)
    st.dataframe(hist_df, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────
# AUTO REFRESH LOOP (rerun page after interval)
# ─────────────────────────────────────────────────────────
if auto_refresh:
    import time as _time
    refresh_secs = refresh_minutes * 60
    st.caption(f"⟳ Auto-refresh active every {refresh_minutes} min. Next scan after idle.")
    _time.sleep(refresh_secs)
    st.rerun()
