import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import math
import os
from datetime import datetime
import textwrap

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI全能預測 (Ultimate Pro Black)", page_icon="⚽", layout="wide")

# ================= CSS =================
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    div[data-testid="stMetric"] { background-color: #262730 !important; border: 1px solid #444; border-radius: 8px; padding: 10px; }
    div[data-testid="stMetricLabel"] p { color: #aaaaaa !important; font-size: 0.9rem; }
    div[data-testid="stMetricValue"] div { color: #ffffff !important; font-size: 1.5rem !important; }
    .css-card-container { background-color: #1a1c24; border: 1px solid #333; border-radius: 12px; padding: 15px; margin-bottom: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }
    h1, h2, h3, h4, span, div, b, p { color: #ffffff !important; font-family: "Source Sans Pro", sans-serif; }
    .sub-text { color: #cccccc !important; font-size: 0.8rem; }
    .h2h-text { color: #ffd700 !important; font-size: 0.8rem; margin-bottom: 3px; font-weight: bold; }
    .ou-stats-text { color: #00ffff !important; font-size: 0.75rem; margin-bottom: 10px; opacity: 0.9; }
    .market-value-text { color: #28a745 !important; font-size: 0.85rem; font-weight: bold; margin-top: 2px; }
    .rank-badge { background-color: #444; color: #fff !important; padding: 1px 5px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; border: 1px solid #666; margin: 0 4px; }
    .form-circle { display: inline-block; width: 18px; height: 18px; line-height: 18px; text-align: center; border-radius: 50%; font-size: 0.65rem; margin: 0 1px; color: white !important; font-weight: bold; border: 1px solid rgba(255,255,255,0.2); }
    .form-w { background-color: #28a745 !important; }
    .form-d { background-color: #ffc107 !important; color: black !important; } 
    .form-l { background-color: #dc3545 !important; }
    .live-status { color: #ff4b4b !important; font-weight: bold; animation: blinker 1.5s linear infinite; }
    @keyframes blinker { 50% { opacity: 0; } }
    .stProgress > div > div > div > div { background-color: #007bff; }
    .match-row { display: flex; align-items: center; justify-content: space-between; width: 100%; }
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
    for char in str(form_str).strip()[-5:]:
        if char.upper() == 'W': html += f'<span class="form-circle form-w">W</span>'
        elif char.upper() == 'D': html += f'<span class="form-circle form-d">D</span>'
        elif char.upper() == 'L': html += f'<span class="form-circle form-l">L</span>'
    return html if html else "<span style='color:#555; font-size:0.7rem;'>---</span>"

def calculate_form_points(form_str):
    if pd.isna(form_str): return 0
    points = 0; count = 0
    for char in str(form_str).strip()[-5:]:
        if char.upper() == 'W': points += 3
        elif char.upper() == 'D': points += 1
        count += 1
    return points / count if count > 0 else 0

def format_market_value(val):
    try:
        clean_val = str(val).replace('€','').replace('M','').replace(',','').strip()
        return f"€{int(float(clean_val))}M"
    except: return str(val) if not pd.isna(val) else ""

def calculate_probabilities(home_exp, away_exp):
    def poisson(k, lam): return (lam**k * math.exp(-lam)) / math.factorial(k)
    home_win=0; draw=0; away_win=0; over=0; under=0
    for h in range(8): 
        for a in range(8): 
            prob = poisson(h, home_exp) * poisson(a, away_exp)
            if h > a: home_win += prob
            elif h == a: draw += prob
            else: away_win += prob
            if h + a > 2.5: over += prob
            else: under += prob
    return {"home_win": home_win*100, "draw": draw*100, "away_win": away_win*100, "over": over*100, "under": under*100}

# ================= 連接 Google Sheet =================
@st.cache_data(ttl=60) 
def load_data():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if os.path.exists("key.json"): creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        else: creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e: 
        st.error(f"連線或讀取錯誤: {e}")
        return None

# ================= 主程式 =================
def main():
    st.title("⚽ 足球AI全能預測 (Ultimate Pro Black)")
    
    # 載入數據
    df = load_data()
    
    # 頂部狀態列
    c1, c2, c3, c4 = st.columns(4)
    if df is not None and not df.empty:
        total_m = len(df)
        live_m = len(df[df['狀態'].astype(str).str.contains("進行中", na=False)])
        finish_m = len(df[df['狀態'] == '完場'])
        c1.metric("總賽事", f"{total_m} 場")
        c2.metric("LIVE 進行中", f"{live_m} 場")
        c3.metric("已完場", f"{finish_m} 場")
    else:
        c1.metric("總賽事", "0 場")
        c2.metric("LIVE 進行中", "0 場")
        c3.metric("已完場", "0 場")

    if c4.button("🔄 刷新數據", use_container_width=True): 
        st.cache_data.clear()
        st.rerun()

    # 數據檢查
    if df is None or df.empty: 
        st.warning("⚠️ 目前無數據，請確認：\n1. `run_me.py` 是否已成功執行並更新 Google Sheet？\n2. 賽事日期範圍是否正確？")
        return

    cols = ['主預測', '客預測', '主攻(H)', '客攻(A)', '賽事風格', '主動量', '客動量']
    for col in cols: 
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    st.sidebar.header("🔍 篩選條件")
    leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
    selected_league = st.sidebar.selectbox("選擇聯賽:", leagues)
    
    df['日期'] = df['時間'].apply(lambda x: str(x).split(' ')[0])
    available_dates = ["全部"] + sorted(list(set(df['日期'])))
    selected_date = st.sidebar.selectbox("📅 選擇日期:", available_dates)

    filtered_df = df.copy()
    if selected_league != "全部": filtered_df = filtered_df[filtered_df['聯賽'] == selected_league]
    if selected_date != "全部": filtered_df = filtered_df[filtered_df['日期'] == selected_date]

    tab1, tab2 = st.tabs(["📅 未開賽 / 進行中", "✅ 已完場 (核對賽果)"])

    def render_matches(target_df):
        if target_df.empty: 
            st.info("在此篩選條件下暫無賽事。")
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

            exp_h = float(row.get('主預測', 0)); exp_a = float(row.get('客預測', 0))
            probs = calculate_probabilities(exp_h, exp_a)
            h_rank = row.get('主排名', '-'); a_rank = row.get('客排名', '-')
            h_val_disp = format_market_value(row.get('主隊身價', ''))
            a_val_disp = format_market_value(row.get('客隊身價', ''))
            
            h_mom = float(row.get('主動量', 0)) if '主動量' in row else 0
            a_mom = float(row.get('客動量', 0)) if '客動量' in row else 0
            h_trend = "📈" if h_mom > 0.3 else "📉" if h_mom < -0.3 else ""
            a_trend = "📈" if a_mom > 0.3 else "📉" if a_mom < -0.3 else ""
            status_icon = '🔴' if '進行中' in str(row['狀態']) else '🟢' if '完場' in str(row['狀態']) else '⚪'
            
            # 波膽讀取 (安全讀取)
            correct_score = row.get('波膽預測', 'N/A')

            analysis_notes = []
            try:
                cv_h = float(str(row.get('主隊身價','')).replace('€','').replace('M','').replace(',',''))
                cv_a = float(str(row.get('客隊身價','')).replace('€','').replace('M','').replace(',',''))
                if cv_h > cv_a * 2.5: analysis_notes.append(f"💰 <b>身價懸殊</b>: 主隊身價是客隊的 {cv_h/cv_a:.1f} 倍！")
                elif cv_a > cv_h * 2.5: analysis_notes.append(f"💰 <b>身價懸殊</b>: 客隊身價是主隊的 {cv_a/cv_h:.1f} 倍！")
            except: pass
            
            if h_mom > 0.5: analysis_notes.append(f"🔥 <b>主隊強勢</b>: 近況表現優於賽季平均 (動量 +{h_mom:.1f})")
            if a_mom > 0.5: analysis_notes.append(f"🔥 <b>客隊強勢</b>: 近況表現優於賽季平均 (動量 +{a_mom:.1f})")

            vol = float(row.get('賽事風格', 0))
            style_tag = "<br><span style='color:#ffc107; font-weight:bold;'>⚡ 賽事風格: 大開大合 (高入球期望)</span>" if vol > 3.0 else "<br><span style='color:#00ffff; font-weight:bold;'>🛡️ 賽事風格: 防守嚴密 (入球偏少)</span>" if 0 < vol < 2.3 else ""
            
            combined_analysis = "<br>".join(analysis_notes) if analysis_notes else "雙方實力接近，勝負取決於臨場發揮。"
            rec_text = '推薦主勝' if probs['home_win'] > 45 else '推薦客勝' if probs['away_win'] > 45 else '勢均力敵'
            rec_color = '#28a745' if '主勝' in rec_text else '#dc3545' if '客勝' in rec_text else '#ffc107'

            html_parts = []
            html_parts.append(f"<div style='margin-top:8px; background-color:#25262b; padding:8px; border-radius:6px; font-size:0.75rem; border:1px solid #333;'>")
            html_parts.append(f"🎯 預期入球: <b style='color:#fff'>{exp_h} : {exp_a}</b>")
            html_parts.append(f"<br>🎲 <b>首選波膽: <span style='color:#00ff00'>{correct_score}</span></b>") 
            html_parts.append(f"<br>💡 綜合建議: <b style='color:{rec_color}!important'>{rec_text}</b>")
            html_parts.append(style_tag)
            html_parts.append(f"<hr style='margin:5px 0; border-top: 1px solid #444;'><span style='color:#ffa500; font-size: 0.7rem;'>{combined_analysis}</span></div>")
            final_html = "".join(html_parts)

            with st.container():
                st.markdown('<div class="css-card-container">', unsafe_allow_html=True)
                col_match, col_ai = st.columns([1.5, 1])
                with col_match:
                    # 這裡加入了 (HKT) 的顯示
                    st.markdown(f"<div class='sub-text'>🕒 {time_part} (HKT) | 🏆 {row['聯賽']}</div>", unsafe_allow_html=True)
                    st.write("") 
                    
                    m_parts = ["<div class='match-row'>", "<div class='team-col-home'>"]
                    m_parts.append(f"<div><span class='rank-badge'>#{h_rank}</span> {h_trend}</div>")
                    m_parts.append(f"<div class='team-name'>{row['主隊']}</div>")
                    m_parts.append(f"<div class='market-value-text'>{h_val_disp}</div>")
                    m_parts.append(f"<div style='margin-top:2px;'>{get_form_html(row.get('主近況', ''))}</div></div>")
                    
                    m_parts.append("<div class='score-col'><div class='score-text'>")
                    s_h = row.get('主分', ''); s_a = row.get('客分', '')
                    display_score = f"{s_h} - {s_a}" if str(s_h) != '' else "VS"
                    m_parts.append(f"{display_score}</div>")
                    
                    live_cls = 'live-status' if '進行中' in str(row['狀態']) else 'sub-text'
                    m_parts.append(f"<div class='{live_cls}' style='margin-top:2px; font-size:0.75rem;'>{status_icon} {row['狀態']}</div></div>")
                    
                    m_parts.append("<div class='team-col-away'>")
                    m_parts.append(f"<div><span class='rank-badge'>#{a_rank}</span> {a_trend}</div>")
                    m_parts.append(f"<div class='team-name'>{row['客隊']}</div>")
                    m_parts.append(f"<div class='market-value-text'>{a_val_disp}</div>")
                    m_parts.append(f"<div style='margin-top:2px;'>{get_form_html(row.get('客近況', ''))}</div></div></div>")
                    
                    st.markdown("".join(m_parts), unsafe_allow_html=True)

                with col_ai:
                    st.markdown("<div style='padding-left: 15px; border-left: 1px solid #444; height: 100%; display:flex; flex-direction:column; justify-content:center;'>", unsafe_allow_html=True)
                    st.markdown(f"<div class='h2h-text'>⚔️ {row.get('H2H','N/A')}</div>", unsafe_allow_html=True)
                    if row.get('大小球統計') != 'N/A': st.markdown(f"<div class='ou-stats-text'>📊 {row['大小球統計']}</div>", unsafe_allow_html=True)
                    st.markdown("<div style='font-size:0.8rem; color:#007bff!important; font-weight:bold; margin-bottom:5px;'>🤖 AI 實時大數據分析</div>", unsafe_allow_html=True)
                    st.progress(probs['home_win']/100, text=f"主 {probs['home_win']:.0f}% | 和 {probs['draw']:.0f}% | 客 {probs['away_win']:.0f}%")
                    st.progress(probs['over']/100, text=f"大 {probs['over']:.0f}% | 細 {probs['under']:.0f}%")
                    st.markdown(final_html, unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True) 
                st.markdown('</div>', unsafe_allow_html=True)

    with tab1: render_matches(filtered_df[filtered_df['狀態'] != '完場'])
    with tab2: render_matches(filtered_df[filtered_df['狀態'] == '完場'])

if __name__ == "__main__":
    main()
