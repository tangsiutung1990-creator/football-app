import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import math
import os
from datetime import datetime

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI全能預測 (Ultimate Pro)", page_icon="⚽", layout="wide")

# 自定義 CSS 讓介面更專業
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .match-card { border: 1px solid #e6e9ef; padding: 20px; border-radius: 15px; background: white; margin-bottom: 20px; }
    .live-status { color: #ff4b4b; font-weight: bold; animation: blinker 1.5s linear infinite; }
    @keyframes blinker { 50% { opacity: 0; } }
    </style>
    """, unsafe_allow_html=True)

# ================= 數學大腦 (泊松分佈) =================
def calculate_probabilities(home_exp, away_exp):
    def poisson(k, lam):
        if lam <= 0: return 0 if k > 0 else 1
        return (lam**k * math.exp(-lam)) / math.factorial(k)

    home_win_prob = 0
    draw_prob = 0
    away_win_prob = 0
    over_25_prob = 0
    under_25_prob = 0

    for h in range(8): # 增加到 8 球提高精準度
        for a in range(8): 
            prob = poisson(h, home_exp) * poisson(a, away_exp)
            if h > a: home_win_prob += prob
            elif h == a: draw_prob += prob
            else: away_win_prob += prob
            
            if h + a > 2.5: over_25_prob += prob
            else: under_25_prob += prob

    return {
        "home_win": home_win_prob * 100,
        "draw": draw_prob * 100,
        "away_win": away_win_prob * 100,
        "over": over_25_prob * 100,
        "under": under_25_prob * 100
    }

# ================= 連接 Google Sheet =================
@st.cache_data(ttl=60) 
def load_data():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if os.path.exists("key.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        else:
            if "gcp_service_account" in st.secrets:
                creds_dict = st.secrets["gcp_service_account"]
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            else:
                st.error("❌ 找不到 Key！請確認 GitHub Secrets 或本地有 key.json")
                return None

        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"連線錯誤: {e}")
        return None

# ================= 主程式 =================
def main():
    st.title("⚽ 足球賽事預測 (Ultimate Pro)")
    
    # 頂部儀表板
    df = load_data()
    if df is not None and not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        total_m = len(df)
        live_m = len(df[df['狀態'].str.contains("進行中", na=False)])
        finish_m = len(df[df['狀態'] == '完場'])
        c1.metric("總賽事數量", f"{total_m} 場")
        c2.metric("即時進行中", f"{live_m} 場", delta_color="inverse")
        c3.metric("已完成賽事", f"{finish_m} 場")
        c4.write("") # 留空
        if c4.button("🔄 刷新數據", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    if df is None or df.empty:
        st.warning("⚠️ 暫時未能讀取數據，請確保 run_me.py 已成功上傳數據到 Google Sheet。")
        return

    # 確保數據類型正確
    numeric_cols = ['主預測', '客預測', '主攻(H)', '客攻(A)']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # --- 側邊欄過濾器 ---
    st.sidebar.header("🔍 篩選與設定")
    
    # 1. 聯賽過濾
    leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
    selected_league = st.sidebar.selectbox("選擇聯賽:", leagues)
    
    # 2. 日期過濾 (對應你要求的 7 天範圍)
    df['日期'] = df['時間'].apply(lambda x: str(x).split(' ')[0])
    available_dates = ["全部"] + sorted(list(set(df['日期'])))
    selected_date = st.sidebar.selectbox("📅 選擇日期 (過去/未來7天):", available_dates)

    # 執行過濾
    filtered_df = df.copy()
    if selected_league != "全部":
        filtered_df = filtered_df[filtered_df['聯賽'] == selected_league]
    if selected_date != "全部":
        filtered_df = filtered_df[filtered_df['日期'] == selected_date]

    # --- 狀態篩選頁籤 ---
    tab1, tab2 = st.tabs(["📅 未開賽 / 進行中", "✅ 已完場 (核對賽果)"])

    def render_matches(target_df, is_finished=False):
        if target_df.empty:
            st.info("暫無相關賽事數據。")
            return

        target_df = target_df.sort_values(by='時間')
        current_date_header = None
        
        for index, row in target_df.iterrows():
            # 日期分組
            date_part = row['日期']
            time_part = str(row['時間']).split(' ')[1] if ' ' in str(row['時間']) else row['時間']

            if date_part != current_date_header:
                current_date_header = date_part
                st.markdown(f"#### 🗓️ {current_date_header}")
                st.divider()

            # 數據準備與機率計算
            exp_h = float(row.get('主預測', 0))
            exp_a = float(row.get('客預測', 0))
            probs = calculate_probabilities(exp_h, exp_a)
            
            # UI 顯示
            with st.container():
                status = row['狀態']
                status_class = "live-status" if "進行中" in status else ""
                status_icon = "🔴" if "進行中" in status else "🟢" if "完場" in status else "⚪"
                
                # 上方資訊列
                st.markdown(f"<span style='color:gray; font-size:0.8rem;'>🕒 {time_part} | {row['聯賽']}</span>", unsafe_allow_html=True)
                
                col_m1, col_m2, col_m3 = st.columns([4, 2, 4])
                with col_m1:
                    st.markdown(f"### **{row['主隊']}**")
                    st.caption(f"主攻指引: {row.get('主攻(H)', 0)}")
                with col_m2:
                    score = f"{row['主分']} - {row['客分']}" if row['主分'] != '' else "VS"
                    st.markdown(f"<h2 style='text-align: center; margin:0;'>{score}</h2>", unsafe_allow_html=True)
                    st.markdown(f"<div style='text-align: center;' class='{status_class}'>{status_icon} {status}</div>", unsafe_allow_html=True)
                with col_m3:
                    st.markdown(f"<div style='text-align: right'><h3><b>{row['客隊']}</b></h3></div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='text-align: right; color: gray;'>客攻指引: {row.get('客攻(A)', 0)}</div>", unsafe_allow_html=True)

                # AI 預測視覺化 (Progress Bars)
                with st.expander("🔮 查看 AI 深度分析與機率"):
                    p_col1, p_col2 = st.columns(2)
                    with p_col1:
                        st.write(f"**勝平負機率 (1X2)**")
                        st.write(f"主勝 {probs['home_win']:.1f}%")
                        st.progress(probs['home_win']/100)
                        st.write(f"和局 {probs['draw']:.1f}%")
                        st.progress(probs['draw']/100)
                        st.write(f"客勝 {probs['away_win']:.1f}%")
                        st.progress(probs['away_win']/100)
                    with p_col2:
                        st.write(f"**大細球機率 (2.5)**")
                        st.write(f"大球 {probs['over']:.1f}%")
                        st.progress(probs['over']/100)
                        st.write(f"細球 {probs['under']:.1f}%")
                        st.progress(probs['under']/100)
                    
                    st.info(f"💡 **AI 建議**：{'🏆 主勝' if probs['home_win'] > 45 else '✈️ 客勝' if probs['away_win'] > 45 else '⚖️ 推薦和局'} | "
                            f"{'🔥 大球可期' if probs['over'] > 60 else '🧊 傾向細球' if probs['under'] > 60 else '中規中矩'}")

                st.markdown("<br>", unsafe_allow_html=True)

    with tab1:
        upcoming_df = filtered_df[filtered_df['狀態'] != '完場']
        render_matches(upcoming_df)

    with tab2:
        finished_df = filtered_df[filtered_df['狀態'] == '完場']
        render_matches(finished_df, is_finished=True)

if __name__ == "__main__":
    main()
