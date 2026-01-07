import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import math
import os
from datetime import datetime

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI全能預測 (Pro Plus)", page_icon="⚽", layout="wide")

# 自定義更高級的 CSS
st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .match-card { 
        border-radius: 15px; 
        background-color: white; 
        padding: 25px; 
        margin-bottom: 20px; 
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        border-left: 5px solid #007BFF;
    }
    .rank-badge {
        background-color: #343a40;
        color: white;
        padding: 2px 8px;
        border-radius: 5px;
        font-size: 0.8rem;
        margin-right: 5px;
    }
    .form-w { background-color: #28a745; color: white; padding: 2px 6px; border-radius: 50%; font-size: 0.7rem; margin: 0 1px; }
    .form-d { background-color: #ffc107; color: black; padding: 2px 6px; border-radius: 50%; font-size: 0.7rem; margin: 0 1px; }
    .form-l { background-color: #dc3545; color: white; padding: 2px 6px; border-radius: 50%; font-size: 0.7rem; margin: 0 1px; }
    .live-status { color: #ff4b4b; font-weight: bold; animation: blinker 1.5s linear infinite; }
    @keyframes blinker { 50% { opacity: 0; } }
    </style>
    """, unsafe_allow_html=True)

# ================= 輔助函式：近況視覺化 =================
def get_form_html(form_str):
    if not form_str or form_str == 'N/A': return "<span style='color:gray'>無數據</span>"
    html = ""
    for char in str(form_str):
        if char == 'W': html += f'<span class="form-w">勝</span>'
        elif char == 'D': html += f'<span class="form-d">和</span>'
        elif char == 'L': html += f'<span class="form-l">負</span>'
    return html

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

    for h in range(8): 
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
                st.error("❌ 找不到 Key！")
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
    st.title("⚽ 足球賽事預測 (Ultimate Pro Plus)")
    
    df = load_data()
    if df is not None and not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        total_m = len(df)
        live_m = len(df[df['狀態'].str.contains("進行中", na=False)])
        finish_m = len(df[df['狀態'] == '完場'])
        c1.metric("總賽事", f"{total_m} 場")
        c2.metric("LIVE 進行中", f"{live_m} 場")
        c3.metric("已完場", f"{finish_m} 場")
        if c4.button("🔄 刷新數據", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    if df is None or df.empty:
        st.warning("⚠️ 數據加載中或 Google Sheet 無內容...")
        return

    # 數據轉型
    numeric_cols = ['主預測', '客預測', '主攻(H)', '客攻(A)']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # --- 側邊欄 ---
    st.sidebar.header("🔍 篩選條件")
    leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
    selected_league = st.sidebar.selectbox("選擇聯賽:", leagues)
    
    df['日期'] = df['時間'].apply(lambda x: str(x).split(' ')[0])
    available_dates = ["全部"] + sorted(list(set(df['日期'])))
    selected_date = st.sidebar.selectbox("📅 選擇日期:", available_dates)

    filtered_df = df.copy()
    if selected_league != "全部":
        filtered_df = filtered_df[filtered_df['聯賽'] == selected_league]
    if selected_date != "全部":
        filtered_df = filtered_df[filtered_df['日期'] == selected_date]

    tab1, tab2 = st.tabs(["📅 未開賽 / 進行中", "✅ 已完場 (核對賽果)"])

    def render_matches(target_df):
        if target_df.empty:
            st.info("暫無相關賽事。")
            return

        target_df = target_df.sort_values(by='時間')
        current_date_header = None
        
        for index, row in target_df.iterrows():
            date_part = row['日期']
            time_part = str(row['時間']).split(' ')[1] if ' ' in str(row['時間']) else row['時間']

            if date_part != current_date_header:
                current_date_header = date_part
                st.markdown(f"#### 🗓️ {current_date_header}")
                st.divider()

            # 計算預測
            exp_h = float(row.get('主預測', 0))
            exp_a = float(row.get('客預測', 0))
            probs = calculate_probabilities(exp_h, exp_a)
            
            # --- 排名與近況 HTML ---
            h_rank = f'<span class="rank-badge">排名: {row["主排名"]}</span>' if row["主排名"] != '-' else ""
            a_rank = f'<span class="rank-badge">排名: {row["客排名"]}</span>' if row["客排名"] != '-' else ""
            h_form = get_form_html(row.get('主近況', 'N/A'))
            a_form = get_form_html(row.get('客近況', 'N/A'))

            # --- 比賽卡片佈局 ---
            with st.container():
                st.markdown(f"""
                <div class="match-card">
                    <div style="color:gray; font-size:0.85rem; margin-bottom:10px;">
                        🕒 {time_part} | 🏆 {row['聯賽']}
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="flex: 1; text-align: left;">
                            {h_rank} <br> <b style="font-size:1.4rem;">{row['主隊']}</b> <br>
                            <span style="font-size:0.8rem;">近況: {h_form}</span>
                        </div>
                        <div style="flex: 0.5; text-align: center;">
                            <h1 style="margin:0; color:#333;">{row['主分'] if row['主分'] != '' else 'vs'} {row['客分'] if row['客分'] != '' else ''}</h1>
                            <span class="{'live-status' if '進行中' in row['狀態'] else ''}" style="font-size:0.9rem;">
                                {'🔴' if '進行中' in row['狀態'] else '🟢' if '完場' in row['狀態'] else '⚪'} {row['狀態']}
                            </span>
                        </div>
                        <div style="flex: 1; text-align: right;">
                            {a_rank} <br> <b style="font-size:1.4rem;">{row['客隊']}</b> <br>
                            <span style="font-size:0.8rem;">近況: {a_form}</span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # --- AI 預測詳情 ---
                with st.expander("📊 展開 AI 深度分析"):
                    c_a, c_b = st.columns(2)
                    with c_a:
                        st.write("**核心勝率預測**")
                        st.progress(probs['home_win']/100, text=f"主勝 {probs['home_win']:.1f}%")
                        st.progress(probs['draw']/100, text=f"和局 {probs['draw']:.1f}%")
                        st.progress(probs['away_win']/100, text=f"客勝 {probs['away_win']:.1f}%")
                    with c_b:
                        st.write("**進球分布預測**")
                        st.progress(probs['over']/100, text=f"大球 (>2.5) {probs['over']:.1f}%")
                        st.progress(probs['under']/100, text=f"細球 (<2.5) {probs['under']:.1f}%")
                        st.caption(f"主隊預測進球: {exp_h} | 客隊預測進球: {exp_a}")
                    
                    # 結合排名的智慧分析
                    rank_diff = 0
                    try:
                        rank_diff = int(row['客排名']) - int(row['主排名'])
                    except: pass
                    
                    analysis_note = "⚖️ 雙方排名接近，預計是一場拉鋸戰。"
                    if rank_diff > 8: analysis_note = "🔥 主隊排名優勢明顯，贏面極大。"
                    elif rank_diff < -8: analysis_note = "✈️ 客隊實力佔優，主隊面臨苦戰。"

                    st.info(f"💡 **AI 綜合分析**：{analysis_note} | 建議方向：**{'推薦主勝' if probs['home_win'] > 45 else '推薦客勝' if probs['away_win'] > 45 else '搏和局'}**")

                st.markdown("<div style='margin-bottom:25px;'></div>", unsafe_allow_html=True)

    with tab1:
        render_matches(filtered_df[filtered_df['狀態'] != '完場'])
    with tab2:
        render_matches(filtered_df[filtered_df['狀態'] == '完場'])

if __name__ == "__main__":
    main()
