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

# ================= CSS 強力修復區 (Flexbox 對齊版) =================
st.markdown("""
    <style>
    /* 1. 全局背景設為深色 */
    .stApp { background-color: #0e1117; }
    
    /* 2. 數據格 (Metric) - 深灰底白字 */
    div[data-testid="stMetric"] {
        background-color: #262730 !important;
        border: 1px solid #444;
        border-radius: 8px;
        padding: 10px;
    }
    div[data-testid="stMetricLabel"] p { color: #aaaaaa !important; }
    div[data-testid="stMetricValue"] div { color: #ffffff !important; }

    /* 3. 卡片容器樣式 - 加強對比度 */
    .css-card-container {
        background-color: #1a1c24; /* 比背景稍亮 */
        border: 1px solid #333;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 15px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.5);
    }

    /* 4. 文字顏色強制為白 */
    h1, h2, h3, h4, span, div, b, p {
        color: #ffffff !important;
        font-family: "Source Sans Pro", sans-serif;
    }
    
    /* 次要文字顏色 (時間、聯賽) - 調亮一點以免睇唔到 */
    .sub-text { color: #cccccc !important; font-size: 0.9rem; }

    /* 5. 排名 Badge */
    .rank-badge {
        background-color: #444;
        color: #fff !important;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: bold;
        border: 1px solid #666;
        vertical-align: middle;
        margin: 0 5px;
    }
    
    /* 6. 近況圈圈 (確保顯示) */
    .form-circle {
        display: inline-block;
        width: 22px;
        height: 22px;
        line-height: 22px;
        text-align: center;
        border-radius: 50%;
        font-size: 0.75rem;
        margin: 0 2px;
        color: white !important; 
        font-weight: bold;
        border: 1px solid rgba(255,255,255,0.2);
    }
    .form-w { background-color: #28a745 !important; }
    .form-d { background-color: #ffc107 !important; color: black !important; } 
    .form-l { background-color: #dc3545 !important; }

    /* 7. 狀態閃爍 */
    .live-status { 
        color: #ff4b4b !important; 
        font-weight: bold; 
        animation: blinker 1.5s linear infinite; 
    }
    @keyframes blinker { 50% { opacity: 0; } }

    /* 8. 進度條樣式微調 */
    .stProgress > div > div > div > div {
        background-color: #007bff;
    }

    /* 9. 關鍵：Flexbox 佈局類別 (解決不平排問題) */
    .match-row {
        display: flex;
        align-items: center; /* 垂直居中 */
        justify-content: space-between;
        width: 100%;
    }
    .team-col-home {
        flex: 1;
        text-align: left; /* 主隊靠左 */
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .team-col-away {
        flex: 1;
        text-align: right; /* 客隊靠右 */
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .score-col {
        flex: 0.8;
        text-align: center;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .team-name {
        font-size: 1.5rem;
        font-weight: bold;
        margin: 5px 0;
        white-space: nowrap; /* 防止換行 */
    }
    </style>
    """, unsafe_allow_html=True)

# ================= 輔助函式：近況視覺化 =================
def get_form_html(form_str):
    # 強制檢查：如果是空的、None 或 nan，顯示無數據
    if pd.isna(form_str) or str(form_str).strip() == '' or str(form_str) == 'N/A':
        return "<span style='color:#666; font-size:0.8rem;'>N/A</span>"
    
    html = ""
    form_str = str(form_str).strip()[-5:] # 只取最後 5 場
    for char in form_str:
        if char.upper() == 'W': html += f'<span class="form-circle form-w">W</span>'
        elif char.upper() == 'D': html += f'<span class="form-circle form-d">D</span>'
        elif char.upper() == 'L': html += f'<span class="form-circle form-l">L</span>'
    
    if html == "": return "<span style='color:#666; font-size:0.8rem;'>-</span>"
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
    st.title("⚽ 足球賽事預測 (Ultimate Pro Black)")
    
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
        st.warning("⚠️ 數據加載中...")
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
            
            # 準備變數
            h_rank = row['主排名'] if str(row['主排名']).isdigit() else "-"
            a_rank = row['客排名'] if str(row['客排名']).isdigit() else "-"
            
            # 近況 HTML (這裡會去呼叫新的 get_form_html 函數，確保顯示)
            h_form_html = get_form_html(row.get('主近況', ''))
            a_form_html = get_form_html(row.get('客近況', ''))
            
            status_icon = '🔴' if '進行中' in row['狀態'] else '🟢' if '完場' in row['狀態'] else '⚪'
            
            # ================= 卡片佈局 (左球隊 | 右AI) =================
            with st.container():
                st.markdown('<div class="css-card-container">', unsafe_allow_html=True)
                
                # 這裡切分成兩欄：左邊 (球隊資訊 60%) | 右邊 (AI 數據 40%)
                col_match, col_ai = st.columns([1.5, 1])
                
                # --- 左欄：球隊與比分 (使用 HTML Flexbox 確保平排) ---
                with col_match:
                    st.markdown(f"<div class='sub-text'>🕒 {time_part} | 🏆 {row['聯賽']}</div>", unsafe_allow_html=True)
                    st.write("") 
                    
                    # 核心改動：使用 .match-row 和 Flexbox 進行排版
                    match_html = f"""
                    <div class="match-row">
                        <div class="team-col-home">
                            <div><span class="rank-badge">#{h_rank}</span></div>
                            <div class="team-name">{row['主隊']}</div>
                            <div style="margin-top:4px;">{h_form_html}</div>
                        </div>
                        
                        <div class="score-col">
                            <div style="font-size:2.2rem; font-weight:bold; line-height:1;">
                                {row['主分'] if row['主分']!='' else 'VS'}
                                <span style="font-size:1rem; color:#aaa!important; vertical-align:middle;">
                                    {'-' if row['主分'] != '' else ''}
                                </span>
                                {row['客分']}
                            </div>
                            <div class="{'live-status' if '進行中' in row['狀態'] else 'sub-text'}" style="margin-top:5px; font-size:0.85rem;">
                                {status_icon} {row['狀態']}
                            </div>
                        </div>
                        
                        <div class="team-col-away">
                            <div><span class="rank-badge">#{a_rank}</span></div>
                            <div class="team-name">{row['客隊']}</div>
                            <div style="margin-top:4px;">{a_form_html}</div>
                        </div>
                    </div>
                    """
                    st.markdown(match_html, unsafe_allow_html=True)

                # --- 右欄：AI 深度分析 (實時顯示) ---
                with col_ai:
                    # 邊框線 + padding
                    st.markdown("<div style='padding-left: 20px; border-left: 1px solid #444; height: 100%; display:flex; flex-direction:column; justify-content:center;'>", unsafe_allow_html=True)
                    st.markdown("<div style='font-size:0.9rem; color:#007bff!important; font-weight:bold; margin-bottom:10px;'>🤖 AI 實時分析</div>", unsafe_allow_html=True)
                    
                    # 勝率條
                    st.progress(probs['home_win']/100, text=f"主勝 {probs['home_win']:.0f}%  |  和 {probs['draw']:.0f}%  |  客 {probs['away_win']:.0f}%")
                    
                    # 大細球
                    st.progress(probs['over']/100, text=f"大球 (>2.5) {probs['over']:.0f}%  |  細球 {probs['under']:.0f}%")
                    
                    # 簡易建議
                    rec_text = '推薦主勝' if probs['home_win'] > 45 else '推薦客勝' if probs['away_win'] > 45 else '勢均力敵'
                    rec_color = '#28a745' if '主勝' in rec_text else '#dc3545' if '客勝' in rec_text else '#ffc107'
                    
                    st.markdown(f"""
                    <div style='margin-top:12px; background-color:#25262b; padding:10px; border-radius:6px; font-size:0.85rem; border:1px solid #333;'>
                        🎯 預期入球: <b style='color:#fff'>{exp_h} : {exp_a}</b><br>
                        💡 綜合建議: <b style='color:{rec_color}!important'>{rec_text}</b>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    st.markdown("</div>", unsafe_allow_html=True) 

                st.markdown('</div>', unsafe_allow_html=True) # End card container

    with tab1:
        render_matches(filtered_df[filtered_df['狀態'] != '完場'])
    with tab2:
        render_matches(filtered_df[filtered_df['狀態'] == '完場'])

if __name__ == "__main__":
    main()
