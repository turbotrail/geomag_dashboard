import streamlit as st
import pandas as pd
import requests
import datetime
import altair as alt

st.set_page_config("Geomagnetic Storm Dashboard", layout="wide")

# --- Utility ---
def get_kp_level_color(kp):
    if kp <= 4:
        return "🟩 G0 (Quiet)"
    elif kp == 5:
        return "🟨 G1 (Minor)"
    elif kp == 6:
        return "🟧 G2 (Moderate)"
    elif kp == 7:
        return "🔴 G3 (Strong)"
    elif kp == 8:
        return "🔴 G4 (Severe)"
    else:
        return "🔴 G5 (Extreme)"

# --- Timezone Toggle ---
tz_option = st.radio("Timezone", options=["IST (Asia/Kolkata)", "UTC"], index=0, horizontal=True)
tz = "Asia/Kolkata" if "IST" in tz_option else "UTC"
now_utc = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
now = now_utc.astimezone(datetime.timezone(datetime.timedelta(hours=5, minutes=30))) if tz == "Asia/Kolkata" else now_utc

# --- Forecast Block Countdown ---
def next_forecast_block(now_time):
    next_hour = ((now_time.hour // 3) + 1) * 3
    next_block_time = now_time.replace(minute=0, second=0, microsecond=0)
    if next_hour < 24:
        next_block_time = next_block_time.replace(hour=next_hour)
    else:
        next_block_time = (next_block_time + datetime.timedelta(days=1)).replace(hour=0)
    return next_block_time

next_block = next_forecast_block(now)
countdown = next_block - now
st.info(f"⏳ Time until next forecast block ({next_block.strftime('%H:%M')} {tz_option}): **{str(countdown).split('.')[0]}**")

# --- Fetch Functions ---
@st.cache_data(ttl=600)
def fetch_kp_index():
    try:
        url = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data)
        df["time_tag"] = pd.to_datetime(df["time_tag"], errors="coerce").dt.tz_localize("UTC").dt.tz_convert(tz)
        df["kp_index"] = pd.to_numeric(df["kp_index"], errors="coerce")
        return df.dropna(subset=["time_tag", "kp_index"])
    except Exception as e:
        st.warning(f"Kp index fetch failed: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def fetch_alerts():
    try:
        url = "https://services.swpc.noaa.gov/products/alerts.json"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data)
        df = df[["issue_datetime", "product_id", "message"]]
        df.columns = ["Issue Time", "Alert Type", "Message"]
        df["Issue Time"] = pd.to_datetime(df["Issue Time"], errors="coerce").dt.tz_localize("UTC").dt.tz_convert(tz)
        return df.dropna(subset=["Issue Time"])
    except Exception as e:
        st.warning(f"Alerts fetch failed: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def fetch_geomag_activity():
    try:
        url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data)
        df.columns = df.iloc[0]
        df = df.iloc[1:].copy()
        df["time_tag"] = pd.to_datetime(df["time_tag"], errors="coerce").dt.tz_localize("UTC").dt.tz_convert(tz)
        df["Kp"] = pd.to_numeric(df["Kp"], errors="coerce")
        df = df.dropna(subset=["time_tag", "Kp"])
        df = df[df["Kp"] >= 5]
        df["G Level"] = df["Kp"].apply(lambda k: f"G{min(int(k) - 4, 5)}")
        return df.sort_values("time_tag", ascending=False)
    except Exception as e:
        st.warning(f"Storm data fetch failed: {e}")
        return pd.DataFrame()

# --- Fetch All ---
kp_df = fetch_kp_index()
alerts_df = fetch_alerts()
storm_df = fetch_geomag_activity()

# --- Header ---
st.title("Geomagnetic Storm Dashboard")
st.markdown("Real-time monitoring of geomagnetic activity, alerts, and Kp index trends from NOAA SWPC.")

# --- Kp Block View ---
st.subheader("📂 Latest Kp Index (Last 24 Hours — Block View)")
if not kp_df.empty:
    kp_recent = kp_df[kp_df["time_tag"] > now - datetime.timedelta(hours=24)]
    kp_hourly = kp_recent[["time_tag", "kp_index"]].set_index("time_tag").resample("3H").mean().reset_index().tail(8)

    st.markdown("#### 🧱 Kp Status Blocks")
    block_cols = st.columns(len(kp_hourly))
    for idx, row in kp_hourly.iterrows():
        kp = row["kp_index"]
        time_str = row["time_tag"].strftime("%H:%M %Z")
        level = get_kp_level_color(kp)
        with block_cols[idx]:
            st.markdown(f"""
                <div style='background-color: {'#4CAF50' if kp < 5 else '#F44336'}; 
                            padding: 12px; border-radius: 8px; text-align: center;
                            font-weight: bold; color: white;'>
                    {time_str}<br/>Kp {kp:.1f}<br/>{level}
                </div>
            """, unsafe_allow_html=True)
else:
    st.info("No recent Kp index data available.")

# --- Storm Events ---
st.subheader("📜 Detected Geomagnetic Storm Events (Kp ≥ 5)")
if not storm_df.empty:
    st.dataframe(
        storm_df[["time_tag", "Kp", "G Level"]],
        use_container_width=True
    )
else:
    st.info("No recent geomagnetic storms detected.")


# --- Alerts ---
st.subheader("⚠️ Recent NOAA Space Weather Alerts")
if not alerts_df.empty:
    for _, alert in alerts_df.sort_values("Issue Time", ascending=False).head(5).iterrows():
        st.warning(
            f"🕒 {alert['Issue Time'].strftime('%Y-%m-%d %H:%M %Z')}\n\n**{alert['Alert Type']}**\n\n{alert['Message']}",
            icon="🚨"
        )
else:
    st.info("No recent alerts available.")

st.caption("📡 Data from NOAA SWPC: https://www.swpc.noaa.gov")