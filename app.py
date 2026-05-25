# app.py — FnO RSI(10) Crossover Screener — Streamlit Dashboard

import streamlit as st
import pandas as pd
from datetime import datetime
import requests
import config
import screener

# Pandas >= 2.1 renamed Styler.applymap → Styler.map
if not hasattr(pd.io.formats.style.Styler, "applymap"):
    pd.io.formats.style.Styler.applymap = pd.io.formats.style.Styler.map

st.set_page_config(
    page_title="FnO RSI Screener",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    [data-testid="metric-container"] {
        background: #1c1b19;
        border: 1px solid #393836;
        border-radius: 8px;
        padding: 12px 16px !important;
    }
    [data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
    [data-testid="stProgress"] > div > div { background-color: #4f98a3 !important; }
    [data-testid="stTabs"] button[aria-selected="true"] {
        color: #4f98a3 !important;
        border-bottom-color: #4f98a3 !important;
    }
    hr { border-color: #393836 !important; }
    section[data-testid="stSidebar"] { background: #1c1b19; }
    [data-testid="stDownloadButton"] button {
        background: #313b3b !important;
        border: 1px solid #4f98a3 !important;
        color: #4f98a3 !important;
    }
</style>
""", unsafe_allow_html=True)


# ─── TELEGRAM ──────────────────────────────────────────────
def send_telegram_alert(results: list) -> bool:
    if not results:
        return False

    crossovers  = [r for r in results if r["Signal"] == "CROSSOVER"]
    crossunders = [r for r in results if r["Signal"] == "CROSSUNDER"]

    lines = [
        "📈 *FnO RSI\(10\) Screener Alert* — 4H Timeframe",
        f"🕐 Scanned at: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST`",
        f"📊 Total Signals Found: *{len(results)}*\n",
    ]

    if crossovers:
        lines.append("🟢 *CROSSOVER — Bullish*")
        for r in crossovers:
            lines.append(
                f"  • `{r['Symbol']}` \| RSI: {r['RSI(10)']} \| SMA: {r['SMA14(RSI10)']} "
                f"\| Close: ₹{r['Close']} \| {r['LastCandle']}"
            )

    if crossunders:
        lines.append("\n🔴 *CROSSUNDER — Bearish*")
        for r in crossunders:
            lines.append(
                f"  • `{r['Symbol']}` \| RSI: {r['RSI(10)']} \| SMA: {r['SMA14(RSI10)']} "
                f"\| Close: ₹{r['Close']} \| {r['LastCandle']}"
            )

    message = "\n".join(lines)
    url     = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"

    try:
        resp = requests.post(url, json={
            "chat_id":    config.TELEGRAM_CHAT_ID,
            "text":       message,
            "parse_mode": "MarkdownV2"
        }, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


# ─── SESSION STATE ─────────────────────────────────────────
for key, default in [
    ("results", []),
    ("last_scan_time", None),
    ("scan_history", []),
    ("alert_sent", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ─── HEADER ────────────────────────────────────────────────
st.title("📈 FnO RSI(10) Crossover Screener")
st.caption("Scans all NSE F&O stocks  ·  RSI(10) vs SMA14(RSI10)  ·  4H Timeframe  ·  Upstox API V3")

c1, c2, c3, c4, c5 = st.columns(5)
with c1: st.metric("RSI Period",  str(config.RSI_PERIOD))
with c2: st.metric("SMA Period",  str(config.SMA_PERIOD))
with c3: st.metric("Timeframe",   "4H")
with c4: st.metric("Days Back",   str(config.DAYS_BACK))
with c5: st.metric("Last Scanned", st.session_state.last_scan_time.strftime("%H:%M:%S") if st.session_state.last_scan_time else "Never")

st.divider()


# ─── SIDEBAR ───────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Settings")

    st.markdown("**Signal Filter**")
    show_crossover  = st.checkbox("🟢 Crossovers",  value=True)
    show_crossunder = st.checkbox("🔴 Crossunders", value=True)

    st.divider()

    st.markdown("**📲 Telegram Alerts**")
    tg_enabled = st.toggle("Enable Telegram Alerts", value=True)
    if st.button("🧪 Test Alert", use_container_width=True):
        dummy = [{"Symbol": "TESTSTOCK", "Signal": "CROSSOVER",
                  "RSI(10)": 54.3, "SMA14(RSI10)": 50.1, "Close": 2345.6,
                  "LastCandle": datetime.now().strftime("%Y-%m-%d %H:%M")}]
        ok = send_telegram_alert(dummy)
        st.success("✅ Test alert sent!") if ok else st.error("❌ Failed — check token & chat ID in config.py")

    st.divider()

    st.markdown("**🔁 Auto Refresh**")
    auto_refresh    = st.toggle("Enable Auto-Refresh", value=False)
    refresh_minutes = st.selectbox("Interval", [60, 120, 240, 480], index=2,
                                   format_func=lambda x: f"Every {x} min ({x//60}H)")

    st.divider()
    st.caption("💡 Update `UPSTOX_ACCESS_TOKEN` in `config.py` every morning.")


# ─── SCAN TRIGGER ──────────────────────────────────────────
trigger_scan = False

btn_col, _ = st.columns([1, 4])
with btn_col:
    if st.button("🔍 Run Scan Now", type="primary", use_container_width=True):
        trigger_scan = True

if auto_refresh and st.session_state.last_scan_time:
    elapsed_min = (datetime.now() - st.session_state.last_scan_time).seconds / 60
    if elapsed_min >= refresh_minutes:
        trigger_scan = True


# ─── RUN SCAN ──────────────────────────────────────────────
if trigger_scan:
    st.session_state.alert_sent = False
    progress_bar = st.progress(0, text="🔄 Loading FnO instrument list...")
    status_box   = st.empty()
    error_box    = st.empty()

    def update_progress(i, total, symbol):
        pct = int((i / total) * 100)
        progress_bar.progress(pct, text=f"Scanning {symbol} ({i}/{total})...")
        status_box.caption(f"⏳ Processing: **{symbol}**")

    try:
        with st.spinner("Running FnO scan on all ~200 stocks..."):
            results = screener.run_scan(progress_callback=update_progress)

        progress_bar.empty()
        status_box.empty()

        st.session_state.results        = results
        st.session_state.last_scan_time = datetime.now()

        st.session_state.scan_history.append({
            "Scanned At":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Total Signals": len(results),
            "🟢 Crossovers":  sum(1 for r in results if r["Signal"] == "CROSSOVER"),
            "🔴 Crossunders": sum(1 for r in results if r["Signal"] == "CROSSUNDER"),
        })

        if results and tg_enabled and not st.session_state.alert_sent:
            ok = send_telegram_alert(results)
            st.session_state.alert_sent = True
            if ok:
                st.toast(f"📲 Telegram alert sent for {len(results)} signal(s)!", icon="✅")
            else:
                st.toast("⚠️ Telegram alert failed — check config.py", icon="❌")

        if results:
            st.success(f"✅ Scan complete — **{len(results)} crossover signal(s)** found!")
        else:
            st.info("ℹ️ Scan complete — No signals found. Telegram alert was NOT sent.")

    except Exception as e:
        progress_bar.empty()
        status_box.empty()
        error_box.error(f"❌ Scan failed: `{str(e)}`\n\nCheck your `UPSTOX_ACCESS_TOKEN` in `config.py`.")


# ─── RESULTS TABLE ─────────────────────────────────────────
results = st.session_state.results

if results:
    df = pd.DataFrame(results)

    if not show_crossover:
        df = df[df["Signal"] != "CROSSOVER"]
    if not show_crossunder:
        df = df[df["Signal"] != "CROSSUNDER"]

    st.subheader(f"📋 Signals Found — {len(df)} stock(s)")

    def highlight_signal(val):
        if val == "CROSSOVER":
            return "background-color: #1a3a1a; color: #6daa45; font-weight: 700;"
        elif val == "CROSSUNDER":
            return "background-color: #3a1a1a; color: #dd6974; font-weight: 700;"
        return ""

    display_cols = ["Symbol", "Signal", "RSI(10)", "SMA14(RSI10)", "Close", "LastCandle"]

    tab1, tab2, tab3 = st.tabs([
        f"🟢 Crossovers ({sum(1 for r in results if r['Signal'] == 'CROSSOVER')})",
        f"🔴 Crossunders ({sum(1 for r in results if r['Signal'] == 'CROSSUNDER')})",
        f"📊 All ({len(df)})"
    ])

    with tab1:
        dfco = df[df["Signal"] == "CROSSOVER"][display_cols]
        if dfco.empty:
            st.info("No Crossover signals.")
        else:
            st.dataframe(
                dfco.style.applymap(highlight_signal, subset=["Signal"]),
                use_container_width=True, hide_index=True)

    with tab2:
        dfcu = df[df["Signal"] == "CROSSUNDER"][display_cols]
        if dfcu.empty:
            st.info("No Crossunder signals.")
        else:
            st.dataframe(
                dfcu.style.applymap(highlight_signal, subset=["Signal"]),
                use_container_width=True, hide_index=True)

    with tab3:
        if df.empty:
            st.info("No signals.")
        else:
            st.dataframe(
                df[display_cols].style.applymap(highlight_signal, subset=["Signal"]),
                use_container_width=True, hide_index=True)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download Results CSV", data=csv,
                       file_name=f"fno_rsi_signals_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                       mime="text/csv")

elif st.session_state.last_scan_time:
    st.info("ℹ️ No signals found in the last scan. Telegram alert was **not** sent.")

else:
    st.markdown("""
    <div style="background:#1c1b19;border:1px solid #393836;border-radius:12px;padding:32px 40px;text-align:center;margin-top:16px;">
        <div style="font-size:48px;margin-bottom:16px;">📡</div>
        <h3 style="color:#cdccca;margin-bottom:8px;">Ready to Scan</h3>
        <p style="color:#797876;max-width:480px;margin:0 auto 20px;">
            Click <strong style="color:#4f98a3;">Run Scan Now</strong> to scan all ~200 NSE F&amp;O stocks,
            compute RSI(10) and SMA14(RSI10) on 4H candles, and surface fresh crossover signals.
            Telegram alert fires <strong>only when signals are found</strong>.
        </p>
        <div style="display:flex;justify-content:center;gap:32px;margin-top:20px;">
            <div><div style="font-size:22px;font-weight:700;color:#4f98a3;">RSI(10)</div><div style="font-size:12px;color:#5a5957;">Wilder's Smoothing</div></div>
            <div><div style="font-size:22px;font-weight:700;color:#4f98a3;">SMA(14)</div><div style="font-size:12px;color:#5a5957;">of RSI(10)</div></div>
            <div><div style="font-size:22px;font-weight:700;color:#4f98a3;">4H</div><div style="font-size:12px;color:#5a5957;">Timeframe</div></div>
            <div><div style="font-size:22px;font-weight:700;color:#4f98a3;">~200</div><div style="font-size:12px;color:#5a5957;">FnO Stocks</div></div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ─── SCAN HISTORY ──────────────────────────────────────────
if st.session_state.scan_history:
    st.divider()
    st.subheader("🕐 Scan History — This Session")
    st.dataframe(pd.DataFrame(st.session_state.scan_history), use_container_width=True, hide_index=True)


# ─── AUTO REFRESH ──────────────────────────────────────────
if auto_refresh and st.session_state.last_scan_time:
    import time as _time
    remaining = refresh_minutes * 60 - (datetime.now() - st.session_state.last_scan_time).seconds
    if remaining > 0:
        st.caption(f"⟳ Auto-refresh active — next scan in ~{remaining // 60}m {remaining % 60}s")
        _time.sleep(min(remaining, 60))
        st.rerun()
    else:
        st.rerun()
