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

st.set_page_config(page_title="足球AI全能預測 (Ultimate Pro V9)", page_icon="⚽", layout="wide")

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
    .postponed-status { color: #888888 !important; font-style: italic; border: 1px dashed #555; padding: 2px 5px; border-radius: 4px; }
    .stProgress > div > div > div > div { background-color: #007bff; }
    .match-row { display: flex; align-items: center; justify-content: space-between; width: 100%; }
    .team-col-home { flex: 1; text-align: left; display: flex; flex-direction: column; justify-content: center; }
    .team-col-away { flex: 1; text-align: right; display: flex; flex-direction: column; justify-content: center; }
    .score-col { flex: 0.8; text-align: center; display: flex; flex-direction: column; justify-content: center; }
    .team-name { font-size: 1.2rem; font-weight: bold; margin: 1px 0; white-space: nowrap; }
    .score-text { font-size: 1.8rem; font-weight: bold; line-height: 1; }
    
    /* V9 新增樣式 */
    .adv-stats-box { background-color: #25262b; padding: 10px; border-radius: 6px; border: 1px solid #444; margin-top: 8px; font-size: 0.75rem; }
    .odds-tag { background-color: #333; padding: 2px 6px; border-radius: 4px; border: 1px solid #555; margin-right: 4px; color: #ddd; }
    .confidence-bar-bg { background-color: #444; height: 6px; border-radius: 3px; margin-top: 4px; width: 100%; }
    .confidence-bar-fill { height: 100%; border-radius: 3px; background: linear-gradient(90deg, #ffc107, #28a745); }
    .analysis-text { color: #e0e0e0; margin-top: 5px; line-height: 1.4; font-size: 0.8rem; }
    
    .goal-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 4px; margin: 8px 0; text-align: center; }
    .goal-item { background: #333; padding: 4px; border-radius: 4px; border: 1px solid #444; }
    .goal-title { font-size: 0.7rem; color: #aaa; }
    .goal-val { font-size: 0.9rem; font-weight: bold; color: #fff; }
    .highlight-goal { border: 1px solid #28a745 !important; background: rgba(40, 167, 69, 0.2) !important; box-shadow: 0 0 5px #28a745; }
    .star-rating { color: #ffc107; font-weight: bold; margin-left: 5px; }
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

WEEKDAY_MAP = { 0: '週一', 1: '週二', 2: '週三', 3: '週四', 4: '週五', 5: '週六', 6: '週日' }
def get_weekday_str(date_str):
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return WEEKDAY_MAP[dt.weekday()]
    except: return ""

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
    st.title("⚽ 足球AI全能預測 (Ultimate Pro V9)")
    
    df = load_data()
    
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

    if df is None or df.empty: 
        st.warning("⚠️ 目前無數據，請確認 run_me.py 是否執行成功。")
        return

    # 確保數值型別正確
    num_cols = ['主預測', '客預測', '主攻(H)', '客攻(A)', '賽事風格', '主動量', '客動量', 'BTTS', '主零封', '客零封', '大球率1.5', '大球率2.5', '大球率3.5', 'OU信心', 'H2H平均球']
    for col in num_cols: 
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
            
        target_df = target_df.sort_values(by='時間', ascending=True)
        current_date_header = None
        
        for index, row in target_df.iterrows():
            date_part = row['日期']
            time_part = str(row['時間']).split(' ')[1] if ' ' in str(row['時間']) else row['時間']
            
            if date_part != current_date_header:
                current_date_header = date_part
                weekday_str = get_weekday_str(date_part)
                st.markdown(f"#### 🗓️ {current_date_header} ({weekday_str})")
                st.divider()

            exp_h = float(row.get('主預測', 0)); exp_a = float(row.get('客預測', 0))
            
            # V9 數據
            prob_o15 = float(row.get('大球率1.5', 0))
            prob_o25 = float(row.get('大球率2.5', 0))
            prob_o35 = float(row.get('大球率3.5', 0))
            
            btts_prob = float(row.get('BTTS', 0))
            ou_conf = float(row.get('OU信心', 50))
            h2h_avg = float(row.get('H2H平均球', 0))
            
            cs_h_prob = float(row.get('主零封', 0))
            cs_a_prob = float(row.get('客零封', 0))
            odds_h = row.get('主賠', '-'); odds_d = row.get('和賠', '-'); odds_a = row.get('客賠', '-')
            
            h_rank = row.get('主排名', '-'); a_rank = row.get('客排名', '-')
            h_val_disp = format_market_value(row.get('主隊身價', ''))
            a_val_disp = format_market_value(row.get('客隊身價', ''))
            
            h_mom = float(row.get('主動量', 0)); a_mom = float(row.get('客動量', 0))
            h_trend = "📈" if h_mom > 0.3 else "📉" if h_mom < -0.3 else ""
            a_trend = "📈" if a_mom > 0.3 else "📉" if a_mom < -0.3 else ""
            
            status_str = str(row['狀態'])
            if '進行中' in status_str: status_icon = '🔴'; status_class = 'live-status'
            elif '完場' in status_str: status_icon = '🟢'; status_class = 'sub-text'
            elif '延期' in status_str or '取消' in status_str: status_icon = '⚠️'; status_class = 'postponed-status'
            else: status_icon = '⚪'; status_class = 'sub-text'
            
            correct_score = row.get('波膽預測', 'N/A')
            vol = float(row.get('賽事風格', 0))

            # === AI 智能分析邏輯 (V9) ===
            analysis_notes = []
            
            # 星級評分
            star_rating = ""
            if ou_conf >= 80 and (prob_o25 > 65 or prob_o25 < 35): star_rating = "⭐⭐⭐⭐⭐"
            elif ou_conf >= 60: star_rating = "⭐⭐⭐⭐"
            elif ou_conf >= 50: star_rating = "⭐⭐⭐"
            else: star_rating = "⭐"
            
            # 1. 盤口智能建議
            if prob_o25 > 65:
                if prob_o35 > 50:
                    analysis_notes.append(f"🔥 <b>入球盛宴</b>: [3.5大] 機率極高，歷史平均 {h2h_avg} 球。")
                else:
                    analysis_notes.append(f"✅ <b>大球格局</b>: 穩健首選 [2.5大]，值博率高。")
            elif prob_o25 < 35:
                analysis_notes.append(f"🛡️ <b>防守格局</b>: 預計入球極少，建議 [細球] 或半場和。")
            else:
                 analysis_notes.append(f"⚖️ <b>中性格局</b>: 建議觀望走地，待水位調整。")
            
            # 2. 信心指數解讀
            if ou_conf < 40:
                analysis_notes.append(f"⚠️ <b>數據衝突</b>: 風格與往績不符，信心不足，避戰為上。")
            elif ou_conf > 85:
                analysis_notes.append(f"🌟 <b>AI 鐵膽</b>: 數學、往績、風格完全一致 (信心 {ou_conf:.0f}%)。")
            
            # 3. H2H 特別提示
            if h2h_avg > 3.2: analysis_notes.append(f"⚔️ <b>對攻慣性</b>: 雙方見面即開火，對賽平均 {h2h_avg} 球。")

            combined_analysis = "<br>".join(analysis_notes) if analysis_notes else "數據中立，建議參考即時賠率。"

            # HTML 構建
            html_parts = []
            html_parts.append(f"<div class='adv-stats-box'>")
            
            html_parts.append(f"<div style='display:flex; justify-content:space-between;'>")
            html_parts.append(f"<span>🎯 預期: <b style='color:#fff'>{exp_h} : {exp_a}</b></span>")
            html_parts.append(f"<span>🎲 波膽: <span style='color:#00ff00'>{correct_score}</span></span>")
            html_parts.append(f"</div>")
            
            # [V9] 大小球矩陣
            c15 = "highlight-goal" if prob_o15 > 75 else ""
            c25 = "highlight-goal" if prob_o25 > 60 else ""
            c35 = "highlight-goal" if prob_o35 > 45 else "" 
            
            html_parts.append(f"<div class='goal-grid'>")
            html_parts.append(f"<div class='goal-item {c15}'><div class='goal-title'>1.5 球</div><div class='goal-val'>{prob_o15}%</div></div>")
            html_parts.append(f"<div class='goal-item {c25}'><div class='goal-title'>2.5 球</div><div class='goal-val'>{prob_o25}%</div></div>")
            html_parts.append(f"<div class='goal-item {c35}'><div class='goal-title'>3.5 球</div><div class='goal-val'>{prob_o35}%</div></div>")
            html_parts.append(f"</div>")
            
            # 信心條與星級
            conf_color = "#28a745" if ou_conf > 60 else "#ffc107" if ou_conf > 40 else "#dc3545"
            html_parts.append(f"<div style='margin-bottom:6px;'>")
            html_parts.append(f"<div style='display:flex; justify-content:space-between; font-size:0.75rem; color:#ccc;'>")
            html_parts.append(f"<span>📊 值博率: <span class='star-rating'>{star_rating}</span></span>")
            html_parts.append(f"<span>信心: {ou_conf:.0f}%</span>")
            html_parts.append(f"</div>")
            html_parts.append(f"<div class='confidence-bar-bg'><div class='confidence-bar-fill' style='width:{min(ou_conf, 100)}%; background:{conf_color};'></div></div>")
            html_parts.append(f"</div>")
            
            html_parts.append(f"<div>⚖️ <span class='odds-tag'>主 {odds_h}</span> <span class='odds-tag'>和 {odds_d}</span> <span class='odds-tag'>客 {odds_a}</span></div>")
            html_parts.append(f"<hr style='margin:6px 0; border-top: 1px solid #444;'>")
            html_parts.append(f"<div class='analysis-text'>{combined_analysis}</div>")
            html_parts.append(f"</div>")
            
            final_html = "".join(html_parts)

            with st.container():
                st.markdown('<div class="css-card-container">', unsafe_allow_html=True)
                col_match, col_ai = st.columns([1.5, 1])
                with col_match:
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
                    
                    m_parts.append(f"<div class='{status_class}' style='margin-top:2px; font-size:0.75rem;'>{status_icon} {status_str}</div></div>")
                    
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
                    
                    st.markdown(final_html, unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True) 
                st.markdown('</div>', unsafe_allow_html=True)

    with tab1: render_matches(filtered_df[filtered_df['狀態'] != '完場'])
    with tab2: render_matches(filtered_df[filtered_df['狀態'] == '完場'])

if __name__ == "__main__":
    main()
