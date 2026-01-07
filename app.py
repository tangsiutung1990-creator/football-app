import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import math
import os
from datetime import datetime

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI全能預測 (Ultimate Pro Plus)", page_icon="⚽", layout="wide")

# ================= CSS 強力修復區 =================
st.markdown("""
    <style>
    /* 1. 全局設定：背景微調，讓卡片更突出 */
    .main { background-color: #0e1117; }
    
    /* 2. 數據格 (Metric) 修復 - 強制白底黑字 */
    div[data-testid="stMetric"] {
        background-color: #ffffff !important;
        border-radius: 10px;
        padding: 15px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }
    /* 標籤文字 (例如：總賽事) 改為深灰色 */
    div[data-testid="stMetricLabel"] p {
        color: #555555 !important;
        font-weight: bold;
    }
    /* 數值文字 (例如：65) 改為純黑色 */
    div[data-testid="stMetricValue"] div {
        color: #000000 !important;
    }

    /* 3. 比賽卡片 (Match Card) 修復 - 強制白底黑字 */
    .match-card { 
        border-radius: 12px; 
        background-color: #ffffff !important; 
        padding: 20px; 
        margin-bottom: 15px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border-left: 6px solid #007BFF;
    }
    
    /* 核心修復：強制卡片內所有文字變成黑色，解決 Dark Mode 看不到字的問題 */
    .match-card, .match-card div, .match-card h1, .match-card h2, .match-card span, .match-card b {
        color: #000000;
        font-family: "Source Sans Pro", sans-serif;
    }

    /* 4. 特殊元件顏色重設 (因為上面強制變黑了，這裡要加回顏色) */
    .sub-text { color: #666666 !important; font-size: 0.85rem; }
    
    /* 排名 Badge */
    .rank-badge {
        background-color: #333333 !important;
        color: #ffffff !important; /* 白字 */
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: bold;
        margin-right: 5px;
    }
    
    /* 近況圈圈 */
    .form-circle {
        display: inline-block;
        width: 20px;
        height: 20px;
        line-height: 20px;
        text-align: center;
        border-radius: 50%;
        font-size: 0.7rem;
        margin: 0 2px;
        color: white !important; /* 白字 */
    }
    .form-w { background-color: #28a745 !important; }
    .form-d { background-color: #ffc107 !important; color: black !important; } /* 和局用黑字 */
    .form-l { background-color: #dc3545 !important; }

    /* 狀態閃爍 */
    .live-status { 
        color: #ff4b4b !important; 
        font-weight: bold; 
        animation: blinker 1.5s linear infinite; 
    }
    @keyframes blinker { 50% { opacity: 0; } }
    </style>
    """, unsafe_allow_html=True)

# ================= 輔助函式：近況視覺化 =================
def get_form_html(form_str):
    if not form_str or str(form_str) == 'N/A': return "<span class='sub-text'>無近況</span>"
    html = ""
    # 只取最後 5 場
    form_str = str(form_str)[-5:]
    for char in form_str:
        if char == 'W': html += f'<span class="form-circle form-w">W</span>'
        elif char == 'D': html += f'<span class="form-circle form-d">D</span>'
        elif char == 'L': html += f'<span class="form-circle form-l">L</span>'
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
        # 顯示頂部數據概覽
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
            
            # --- 準備變數 ---
            h_rank_txt = f"#{row['主排名']}" if str(row['主排名']).isdigit() else ""
            a_rank_txt = f"#{row['客排名']}" if str(row['客排名']).isdigit() else ""
            
            h_rank_html = f'<span class="rank-badge">{h_rank_txt}</span>' if h_rank_txt else ""
            a_rank_html = f'<span class="rank-badge">{a_rank_txt}</span>' if a_rank_txt else ""
            
            h_form = get_form_html(row.get('主近況', 'N/A'))
            a_form = get_form_html(row.get('客近況', 'N/A'))
            
            status_icon = '🔴' if '進行中' in row['狀態'] else '🟢' if '完場' in row['狀態'] else '⚪'
            status_class = 'live-status' if '進行中' in row['狀態'] else 'sub-text'

            # --- 修正 HTML 結構 (移除縮排以防變代碼) ---
            card_html = f"""
<div class="match-card">
    <div class="sub-text" style="margin-bottom:10px;">🕒 {time_part} | 🏆 {row['聯賽']}</div>
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div style="flex: 1; text-align: left;">
            {h_rank_html}
            <div style="font-size:1.4rem; font-weight:bold; margin:5px 0;">{row['主隊']}</div>
            <div>{h_form}</div>
        </div>
        <div style="flex: 0.6; text-align: center;">
            <h1 style="margin:0; font-size: 2rem;">
                {row['主分'] if row['主分'] != '' else 'VS'}
                <span style="font-size:1rem; vertical-align:middle;">{'-' if row['主分'] != '' else ''}</span>
                {row['客分'] if row['客分'] != '' else ''}
            </h1>
            <div class="{status_class}" style="margin-top:5px;">{status_icon} {row['狀態']}</div>
        </div>
        <div style="flex: 1; text-align: right;">
            {a_rank_html}
            <div style="font-size:1.4rem; font-weight:bold; margin:5px 0;">{row['客隊']}</div>
            <div>{a_form}</div>
        </div>
    </div>
</div>
"""
            st.markdown(card_html, unsafe_allow_html=True)

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
                    st.caption(f"🎯 預期進球: 主 {exp_h} : 客 {exp_a}")
                
                # 簡單分析邏輯
                rank_diff = 0
                try:
                    r_h = int(row['主排名'])
                    r_a = int(row['客排名'])
                    rank_diff = r_a - r_h 
                except: 
                    pass
                
                analysis_note = "⚖️ 實力接近，勝負難料。"
                if rank_diff > 8: analysis_note = "🔥 主隊排名大幅領先，看好主場優勢。"
                elif rank_diff < -8: analysis_note = "✈️ 客隊排名大幅領先，看好客隊取分。"
                elif probs['over'] > 60: analysis_note = "💥 雙方攻力強勁，有望上演入球騷。"

                rec_text = '推薦主勝' if probs['home_win'] > 45 else '推薦客勝' if probs['away_win'] > 45 else '搏和局/大球'
                st.info(f"💡 **AI 綜合分析**：{analysis_note} | 建議方向：**{rec_text}**")

            st.markdown("<div style='margin-bottom:20px;'></div>", unsafe_allow_html=True)

    with tab1:
        render_matches(filtered_df[filtered_df['狀態'] != '完場'])
    with tab2:
        render_matches(filtered_df[filtered_df['狀態'] == '完場'])

if __name__ == "__main__":
    main()
