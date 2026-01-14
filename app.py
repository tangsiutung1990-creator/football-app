import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import math
import os
from datetime import datetime

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI Alpha Ultra (V15.4)", page_icon="⚽", layout="wide")

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
    .h2h-text { color: #ffd700 !important; font-size: 0.75rem; margin-bottom: 3px; font-weight: bold; letter-spacing: 1px; }
    .market-value-text { color: #28a745 !important; font-size: 0.85rem; font-weight: bold; margin-top: 2px; }
    .rank-badge { background-color: #444; color: #fff !important; padding: 1px 5px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; border: 1px solid #666; margin: 0 4px; }
    .form-circle { display: inline-block; width: 18px; height: 18px; line-height: 18px; text-align: center; border-radius: 50%; font-size: 0.65rem; margin: 0 1px; color: white !important; font-weight: bold; border: 1px solid rgba(255,255,255,0.2); }
    .form-w { background-color: #28a745 !important; }
    .form-d { background-color: #ffc107 !important; color: black !important; } 
    .form-l { background-color: #dc3545 !important; }
    .live-status { color: #ff4b4b !important; font-weight: bold; animation: blinker 1.5s linear infinite; }
    @keyframes blinker { 50% { opacity: 0; } }
    
    /* V15.4 UI */
    .adv-stats-box { background-color: #25262b; padding: 12px; border-radius: 6px; border: 1px solid #444; margin-top: 8px; font-size: 0.8rem; }
    .section-title { font-size: 0.85rem; font-weight: bold; color: #ff9800; border-bottom: 1px solid #444; padding-bottom: 3px; margin-bottom: 6px; margin-top: 6px; }
    .odds-row { display: flex; justify-content: space-between; margin-bottom: 4px; font-size: 0.8rem; }
    .odds-val { color: #fff; font-weight: bold; }
    .min-odds-val { color: #00bfff; font-weight: bold; border-bottom: 1px dashed #00bfff; }
    
    .prob-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; margin: 8px 0; text-align: center; }
    .prob-item { background: #333; padding: 5px; border-radius: 4px; border: 1px solid #444; }
    .prob-title { font-size: 0.7rem; color: #aaa; margin-bottom: 2px; }
    .prob-val { font-size: 0.9rem; font-weight: bold; color: #fff; }
    .prob-sub { font-size: 0.7rem; color: #00ffea; }
    .highlight-prob { border: 1px solid #28a745 !important; background: rgba(40, 167, 69, 0.15) !important; }
    
    .smart-tag { display: inline-block; background: #444; border-radius: 3px; padding: 1px 6px; font-size: 0.75rem; margin-right: 4px; color: #fff; border: 1px solid #555; }
    .risk-badge { font-weight: bold; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; color:#fff; }
    .risk-low { background-color: #28a745; border: 1px solid #1e7e34; }
    .risk-med { background-color: #17a2b8; border: 1px solid #117a8b; }
    .risk-high { background-color: #dc3545; border: 1px solid #bd2130; }
    
    .top-pick-box { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 12px; border-radius: 6px; text-align: center; margin-bottom: 10px; border: 1px solid #8e44ad; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    .top-pick-title { font-size: 0.8rem; color: #eee; font-weight:bold; letter-spacing: 1px; }
    .top-pick-val { font-size: 1.4rem; font-weight: 900; color: #fff; text-shadow: 0 2px 4px rgba(0,0,0,0.5); margin-top: 2px; }
    
    .xg-badge { font-size: 0.75rem; color: #00ffea; background: #333; padding: 1px 4px; border-radius: 3px; border: 1px solid #444; margin-left: 5px; }
    .handicap-box { border: 1px dashed #666; padding: 4px; text-align: center; font-size: 0.75rem; margin-top: 5px; color: #ccc; }
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
    st.title("⚽ 足球AI Alpha Ultra (V15.4)")
    
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

    num_cols = ['xG主', 'xG客', '大球率1.5', '大球率2.5', '大球率3.5', '合理主賠', '合理和賠', '合理客賠', '最低賠率主', '最低賠率客', '最低賠率大1.5', '最低賠率大2.5', '最低賠率大3.5', '主導指數', '入球區間低', '入球區間高']
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

            xg_h = float(row.get('xG主', 0)); xg_a = float(row.get('xG客', 0))
            p15 = float(row.get('大球率1.5', 0)); p25 = float(row.get('大球率2.5', 0)); p35 = float(row.get('大球率3.5', 0))
            
            min_h = float(row.get('最低賠率主', 99)); min_a = float(row.get('最低賠率客', 99))
            min_o15 = float(row.get('最低賠率大1.5', 99)); min_o25 = float(row.get('最低賠率大2.5', 99)); min_o35 = float(row.get('最低賠率大3.5', 99))
            fair_h = float(row.get('合理主賠', 99)); fair_d = float(row.get('合理和賠', 99)); fair_a = float(row.get('合理客賠', 99))
            
            range_l = float(row.get('入球區間低', 0)); range_h = float(row.get('入球區間高', 0))
            
            def fmt_odd(val): return f"{val:.2f}" if val < 50 else "---"
            
            h2h_text = row.get('H2H', 'N/A')
            live_strat = row.get('走地策略', '中性觀望')
            smart_tags = row.get('智能標籤', '')
            risk_level = row.get('風險評級', '值博')
            top_pick = row.get('首選推介', '數據分析中')
            handicap = row.get('亞盤建議', '---'); corners = row.get('角球預測', '---')
            
            h_rank = row.get('主排名', '-'); a_rank = row.get('客排名', '-')
            h_val_disp = format_market_value(row.get('主隊身價', ''))
            a_val_disp = format_market_value(row.get('客隊身價', ''))
            
            status_str = str(row['狀態'])
            if '進行中' in status_str: status_icon = '🔴'; status_class = 'live-status'
            elif '完場' in status_str: status_icon = '🟢'; status_class = 'sub-text'
            else: status_icon = '⚪'; status_class = 'sub-text'
            
            html_parts = []
            html_parts.append(f"<div class='adv-stats-box'>")
            
            # Top Pick
            html_parts.append(f"<div class='top-pick-box'><div class='top-pick-title'>🎯 Alpha Ultra 絕殺</div><div class='top-pick-val'>{top_pick}</div></div>")
            
            # Tags
            risk_class = "risk-low" if "極穩" in risk_level else "risk-high" if "高險" in risk_level else "risk-med"
            tags_html = "".join([f"<span class='smart-tag'>{t}</span>" for t in smart_tags.split(' ') if t])
            html_parts.append(f"<div style='margin-bottom:10px;'><span class='risk-badge {risk_class}'>{risk_level}</span> {tags_html}</div>")
            
            # 入球概率矩陣
            html_parts.append(f"<div class='section-title'>⚽ 入球概率矩陣 (Confidence: {range_l}-{range_h})</div>")
            html_parts.append(f"<div class='prob-grid'>")
            
            c15 = "highlight-prob" if p15 > 75 else ""
            html_parts.append(f"<div class='prob-item {c15}'><div class='prob-title'>1.5大 ({p15:.0f}%)</div><div class='prob-val'>{fmt_odd(100/p15) if p15>0 else '---'}</div><div class='prob-sub'>需 > {fmt_odd(min_o15)}</div></div>")
            
            c25 = "highlight-prob" if p25 > 55 else ""
            html_parts.append(f"<div class='prob-item {c25}'><div class='prob-title'>2.5大 ({p25:.0f}%)</div><div class='prob-val'>{fmt_odd(100/p25) if p25>0 else '---'}</div><div class='prob-sub'>需 > {fmt_odd(min_o25)}</div></div>")
            
            c35 = "highlight-prob" if p35 > 40 else ""
            html_parts.append(f"<div class='prob-item {c35}'><div class='prob-title'>3.5大 ({p35:.0f}%)</div><div class='prob-val'>{fmt_odd(100/p35) if p35>0 else '---'}</div><div class='prob-sub'>需 > {fmt_odd(min_o35)}</div></div>")
            html_parts.append(f"</div>")

            # 價值模型
            html_parts.append(f"<div class='section-title'>💰 獨贏價值 (需高於 Min Odds)</div>")
            html_parts.append(f"<div class='odds-row'><span>Fair: {fmt_odd(fair_h)} / {fmt_odd(fair_d)} / {fmt_odd(fair_a)}</span></div>")
            html_parts.append(f"<div class='odds-row'><span>主 > <span class='min-odds-val'>{fmt_odd(min_h)}</span></span> <span>客 > <span class='min-odds-val'>{fmt_odd(min_a)}</span></span></div>")
            
            # 亞盤與角球
            html_parts.append(f"<div class='handicap-box'>亞盤建議: <b style='color:#fff'>{handicap}</b> | 角球: <b style='color:#fff'>{corners}</b></div>")
            
            html_parts.append(f"<div style='margin-top:8px; font-size:0.75rem; text-align:center; color:#888;'>策略: <span style='color:#fff'>{live_strat}</span></div>")
            html_parts.append(f"</div>")
            final_html = "".join(html_parts)

            with st.container():
                st.markdown('<div class="css-card-container">', unsafe_allow_html=True)
                col_match, col_ai = st.columns([4, 6])
                
                with col_match:
                    st.markdown(f"<div class='sub-text'>🕒 {time_part} | 🏆 {row['聯賽']}</div>", unsafe_allow_html=True)
                    st.write("") 
                    
                    m_parts = ["<div class='match-row'>", "<div class='team-col-home'>"]
                    m_parts.append(f"<div><span class='rank-badge'>#{h_rank}</span><span class='xg-badge'>xG:{xg_h}</span></div>")
                    m_parts.append(f"<div class='team-name'>{row['主隊']}</div>")
                    m_parts.append(f"<div class='market-value-text'>{h_val_disp}</div>")
                    m_parts.append(f"<div style='margin-top:2px;'>{get_form_html(row.get('主近況', ''))}</div></div>")
                    
                    m_parts.append("<div class='score-col'><div class='score-text'>")
                    s_h = row.get('主分', ''); s_a = row.get('客分', '')
                    display_score = f"{s_h} - {s_a}" if str(s_h) != '' else "VS"
                    m_parts.append(f"{display_score}</div>")
                    m_parts.append(f"<div class='{status_class}' style='margin-top:2px; font-size:0.75rem;'>{status_icon} {status_str}</div></div>")
                    
                    m_parts.append("<div class='team-col-away'>")
                    m_parts.append(f"<div><span class='rank-badge'>#{a_rank}</span><span class='xg-badge'>xG:{xg_a}</span></div>")
                    m_parts.append(f"<div class='team-name'>{row['客隊']}</div>")
                    m_parts.append(f"<div class='market-value-text'>{a_val_disp}</div>")
                    m_parts.append(f"<div style='margin-top:2px;'>{get_form_html(row.get('客近況', ''))}</div></div></div>")
                    
                    st.markdown("".join(m_parts), unsafe_allow_html=True)
                    st.markdown(f"<div style='margin-top:10px; text-align:center;'><div class='h2h-text'>對賽: {h2h_text}</div></div>", unsafe_allow_html=True)

                with col_ai:
                    st.markdown("<div style='padding-left: 5px;'>", unsafe_allow_html=True)
                    st.markdown(final_html, unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True) 
                st.markdown('</div>', unsafe_allow_html=True)

    with tab1: render_matches(filtered_df[filtered_df['狀態'] != '完場'])
    with tab2: render_matches(filtered_df[filtered_df['狀態'] == '完場'])

if __name__ == "__main__":
    main()
