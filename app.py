import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import math
import os
from datetime import datetime

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI全能預測 (Ultimate Pro Black)", page_icon="⚽", layout="wide")

# ================= CSS 強力修復區 =================
st.markdown("""
    <style>
    /* 1. 全局背景設為深色 */
    .stApp { background-color: #0e1117; }
    
    /* 2. 數據格 (Metric) */
    div[data-testid="stMetric"] {
        background-color: #262730 !important;
        border: 1px solid #444;
        border-radius: 8px;
        padding: 10px;
    }
    div[data-testid="stMetricLabel"] p { color: #aaaaaa !important; font-size: 0.9rem; }
    div[data-testid="stMetricValue"] div { color: #ffffff !important; font-size: 1.5rem !important; }

    /* 3. 卡片容器 */
    .css-card-container {
        background-color: #1a1c24;
        border: 1px solid #333;
        border-radius: 12px;
        padding: 15px; 
        margin-bottom: 12px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.5);
    }

    /* 4. 文字顏色強制為白 */
    h1, h2, h3, h4, span, div, b, p {
        color: #ffffff !important;
        font-family: "Source Sans Pro", sans-serif;
    }
    
    /* 次要文字顏色 */
    .sub-text { color: #cccccc !important; font-size: 0.8rem; }
    
    /* H2H 文字樣式 (金色) */
    .h2h-text { 
        color: #ffd700 !important; 
        font-size: 0.8rem; 
        margin-bottom: 3px; 
        font-weight: bold;
        letter-spacing: 0.5px;
        text-shadow: 0px 0px 5px rgba(255, 215, 0, 0.3);
    }
    
    /* 大小球統計樣式 (淺藍色) */
    .ou-stats-text {
        color: #00ffff !important;
        font-size: 0.75rem;
        margin-bottom: 10px; 
        font-weight: normal;
        letter-spacing: 0.5px;
        opacity: 0.9;
    }
    
    /* 身價樣式 (綠色) */
    .market-value-text {
        color: #28a745 !important;
        font-size: 0.85rem;
        font-weight: bold;
        margin-top: 2px;
        margin-bottom: 4px;
        text-shadow: 0px 0px 5px rgba(40, 167, 69, 0.2);
    }

    /* 5. 排名 Badge */
    .rank-badge {
        background-color: #444;
        color: #fff !important;
        padding: 1px 5px;
        border-radius: 4px;
        font-size: 0.7rem; 
        font-weight: bold;
        border: 1px solid #666;
        vertical-align: middle;
        margin: 0 4px;
    }
    
    /* 6. 近況圈圈 */
    .form-circle {
        display: inline-block;
        width: 18px; 
        height: 18px;
        line-height: 18px;
        text-align: center;
        border-radius: 50%;
        font-size: 0.65rem; 
        margin: 0 1px;
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

    /* 8. 進度條 */
    .stProgress > div > div > div > div {
        background-color: #007bff;
    }

    /* 9. Flexbox 佈局 */
    .match-row {
        display: flex;
        align-items: center; 
        justify-content: space-between;
        width: 100%;
    }
    .team-col-home { flex: 1; text-align: left; display: flex; flex-direction: column; justify-content: center; }
    .team-col-away { flex: 1; text-align: right; display: flex; flex-direction: column; justify-content: center; }
    .score-col { flex: 0.8; text-align: center; display: flex; flex-direction: column; justify-content: center; }
    .team-name { font-size: 1.2rem; font-weight: bold; margin: 1px 0; white-space: nowrap; }
    .score-text { font-size: 1.8rem; font-weight: bold; line-height: 1; }
    </style>
    """, unsafe_allow_html=True)

# ================= 輔助函式 =================
def get_form_html(form_str):
    if pd.isna(form_str) or str(form_str).strip() == '' or str(form_str) == 'N/A' or str(form_str) == 'None':
        return "<span style='color:#555; font-size:0.7rem;'>---</span>"
    
    html = ""
    form_str = str(form_str).strip()[-5:]
    for char in form_str:
        if char.upper() == 'W': html += f'<span class="form-circle form-w">W</span>'
        elif char.upper() == 'D': html += f'<span class="form-circle form-d">D</span>'
        elif char.upper() == 'L': html += f'<span class="form-circle form-l">L</span>'
    
    if html == "": return "<span style='color:#555; font-size:0.7rem;'>---</span>"
    return html

def calculate_form_points(form_str):
    if pd.isna(form_str) or str(form_str).strip() == '' or str(form_str) == 'N/A': return 0
    points = 0; count = 0
    form_str = str(form_str).strip()[-5:]
    for char in form_str:
        if char.upper() == 'W': points += 3
        elif char.upper() == 'D': points += 1
        count += 1
    return points / count if count > 0 else 0

def format_market_value(val):
    if pd.isna(val) or val == '' or str(val).upper() == 'N/A' or str(val).upper() == 'NONE': return ""
    try:
        clean_val = str(val).replace('€','').replace('M','').replace(',','').strip()
        num_val = float(clean_val)
        return f"€{int(num_val)}M"
    except: return str(val)

# ================= 數學大腦 =================
def calculate_probabilities(home_exp, away_exp):
    def poisson(k, lam):
        if lam <= 0: return 0 if k > 0 else 1
        return (lam**k * math.exp(-lam)) / math.factorial(k)

    home_win_prob = 0; draw_prob = 0; away_win_prob = 0
    over_25_prob = 0; under_25_prob = 0

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
    st.title("⚽ 足球AI全能預測 (Ultimate Pro Black)")
    
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
        st.warning("⚠️ 數據加載中...")
        return

    # 確保數值欄位為數字 (包含新加入的賽事風格、主客動量)
    numeric_cols = ['主預測', '客預測', '主攻(H)', '客攻(A)', '賽事風格', '主動量', '客動量']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

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

            exp_h = float(row.get('主預測', 0))
            exp_a = float(row.get('客預測', 0))
            probs = calculate_probabilities(exp_h, exp_a)
            
            h_rank = row['主排名'] if str(row['主排名']).isdigit() else "-"
            a_rank = row['客排名'] if str(row['客排名']).isdigit() else "-"
            h_form_html = get_form_html(row.get('主近況', ''))
            a_form_html = get_form_html(row.get('客近況', ''))
            status_icon = '🔴' if '進行中' in row['狀態'] else '🟢' if '完場' in row['狀態'] else '⚪'
            
            # --- 讀取與分析 ---
            h2h_info = row.get('H2H', 'N/A')
            h2h_display = f"⚔️ {h2h_info}" if not pd.isna(h2h_info) and str(h2h_info) not in ['None','N/A',''] else '<span style="color:#666;">對賽往績: N/A</span>'
            
            ou_stats_info = row.get('大小球統計', 'N/A')
            ou_display = f"📊 {ou_stats_info}" if not pd.isna(ou_stats_info) and str(ou_stats_info) not in ['None','N/A',''] else ""
            
            raw_h_val = row.get('主隊身價', 'N/A')
            raw_a_val = row.get('客隊身價', 'N/A')
            h_value_display = format_market_value(raw_h_val)
            a_value_display = format_market_value(raw_a_val)

            # 動量指標 (Momentum) 顯示
            h_mom = float(row.get('主動量', 0)) if '主動量' in row else 0
            a_mom = float(row.get('客動量', 0)) if '客動量' in row else 0
            h_trend = "📈" if h_mom > 0.3 else "📉" if h_mom < -0.3 else ""
            a_trend = "📈" if a_mom > 0.3 else "📉" if a_mom < -0.3 else ""

            analysis_notes = []
            
            # 1. 身價分析
            try:
                clean_h = str(raw_h_val).replace('€','').replace('M','').replace(',','').strip()
                clean_a = str(raw_a_val).replace('€','').replace('M','').replace(',','').strip()
                if clean_h and clean_a and clean_h != 'N/A' and clean_a != 'N/A':
                    h_v_num = float(clean_h); a_v_num = float(clean_a)
                    if h_v_num > a_v_num * 2.5: analysis_notes.append(f"💰 <b>身價懸殊</b>: 主隊身價是客隊的 {h_v_num/a_v_num:.1f} 倍，紙面實力碾壓！")
                    elif a_v_num > h_v_num * 2.5: analysis_notes.append(f"💰 <b>身價懸殊</b>: 客隊身價是主隊的 {a_v_num/h_v_num:.1f} 倍，客隊質素佔優！")
            except: pass 

            # 2. 動量分析 (Momentum)
            if h_mom > 0.5: analysis_notes.append(f"🔥 <b>主隊強勢</b>: 近況表現優於賽季平均 (動量 +{h_mom:.1f})")
            if a_mom > 0.5: analysis_notes.append(f"🔥 <b>客隊強勢</b>: 近況表現優於賽季平均 (動量 +{a_mom:.1f})")
            
            # 3. 風格分析 (Volatility)
            volatility = float(row.get('賽事風格', 0))
            style_tag = ""
            if volatility > 3.0:
                style_tag = "<br><span style='color:#ffc107; font-weight:bold;'>⚡ 賽事風格: 大開大合 (高入球期望)</span>"
            elif volatility > 0 and volatility < 2.3:
                style_tag = "<br><span style='color:#00ffff; font-weight:bold;'>🛡️ 賽事風格: 防守嚴密 (入球偏少)</span>"

            combined_analysis = "<br>".join(analysis_notes) if analysis_notes else "雙方實力接近，勝負取決於臨場發揮。"

            rec_text = '推薦主勝' if probs['home_win'] > 45 else '推薦客勝' if probs['away_win'] > 45 else '勢均力敵'
            rec_color = '#28a745' if '主勝' in rec_text else '#dc3545' if '客勝' in rec_text else '#ffc107'

            # --- 單行拼接 HTML (確保顯示無 Bug) ---
            html_parts = []
            html_parts.append(f"<div style='margin-top:8px; background-color:#25262b; padding:8px; border-radius:6px; font-size:0.75rem; border:1px solid #333;'>")
            html_parts.append(f"🎯 預期入球: <b style='color:#fff'>{exp_h} : {exp_a}</b><br>")
            html_parts.append(f"💡 綜合建議: <b style='color:{rec_color}!important'>{rec_text}</b>")
            html_parts.append(style_tag)
            html_parts.append(f"<hr style='margin:5px 0; border-top: 1px solid #444;'>")
            html_parts.append(f"<span style='color:#ffa500; font-size: 0.7rem;'>{combined_analysis}</span>")
            html_parts.append("</div>")
            
            final_html = "".join(html_parts)

            with st.container():
                st.markdown('<div class="css-card-container">', unsafe_allow_html=True)
                
                col_match, col_ai = st.columns([1.5, 1])
                
                with col_match:
                    st.markdown(f"<div class='sub-text'>🕒 {time_part} | 🏆 {row['聯賽']}</div>", unsafe_allow_html=True)
                    st.write("") 
                    
                    # 比賽資訊區塊
                    m_parts = []
                    m_parts.append("<div class='match-row'>")
                    
                    # 主隊
                    m_parts.append("<div class='team-col-home'>")
                    m_parts.append(f"<div><span class='rank-badge'>#{h_rank}</span> {h_trend}</div>")
                    m_parts.append(f"<div class='team-name'>{row['主隊']}</div>")
                    m_parts.append(f"<div class='market-value-text'>{h_value_display}</div>")
                    m_parts.append(f"<div style='margin-top:2px;'>{h_form_html}</div>")
                    m_parts.append("</div>")
                    
                    # 比分
                    m_parts.append("<div class='score-col'>")
                    m_parts.append("<div class='score-text'>")
                    m_parts.append(f"{row['主分'] if row['主分']!='' else 'VS'}")
                    m_parts.append(f"<span style='font-size:0.9rem; color:#aaa!important; vertical-align:middle;'>{'-' if row['主分'] != '' else ''}</span>")
                    m_parts.append(f"{row['客分']}")
                    m_parts.append("</div>")
                    live_cls = 'live-status' if '進行中' in row['狀態'] else 'sub-text'
                    m_parts.append(f"<div class='{live_cls}' style='margin-top:2px; font-size:0.75rem;'>{status_icon} {row['狀態']}</div>")
                    m_parts.append("</div>")
                    
                    # 客隊
                    m_parts.append("<div class='team-col-away'>")
                    m_parts.append(f"<div><span class='rank-badge'>#{a_rank}</span> {a_trend}</div>")
                    m_parts.append(f"<div class='team-name'>{row['客隊']}</div>")
                    m_parts.append(f"<div class='market-value-text'>{a_value_display}</div>")
                    m_parts.append(f"<div style='margin-top:2px;'>{a_form_html}</div>")
                    m_parts.append("</div></div>")
                    
                    match_html = "".join(m_parts)
                    st.markdown(match_html, unsafe_allow_html=True)

                with col_ai:
                    st.markdown("<div style='padding-left: 15px; border-left: 1px solid #444; height: 100%; display:flex; flex-direction:column; justify-content:center;'>", unsafe_allow_html=True)
                    
                    st.markdown(f"<div class='h2h-text'>{h2h_display}</div>", unsafe_allow_html=True)
                    if ou_display: st.markdown(f"<div class='ou-stats-text'>{ou_display}</div>", unsafe_allow_html=True)

                    st.markdown("<div style='font-size:0.8rem; color:#007bff!important; font-weight:bold; margin-bottom:5px;'>🤖 AI 實時大數據分析</div>", unsafe_allow_html=True)
                    
                    st.progress(probs['home_win']/100, text=f"主 {probs['home_win']:.0f}% | 和 {probs['draw']:.0f}% | 客 {probs['away_win']:.0f}%")
                    st.progress(probs['over']/100, text=f"大 {probs['over']:.0f}% | 細 {probs['under']:.0f}%")
                    
                    # 渲染 HTML
                    st.markdown(final_html, unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True) 

                st.markdown('</div>', unsafe_allow_html=True)

    with tab1:
        render_matches(filtered_df[filtered_df['狀態'] != '完場'])
    with tab2:
        render_matches(filtered_df[filtered_df['狀態'] == '完場'])

if __name__ == "__main__":
    main()
