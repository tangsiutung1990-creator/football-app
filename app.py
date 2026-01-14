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

st.set_page_config(page_title="足球AI Alpha Pro (V15.0)", page_icon="⚽", layout="wide")

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
    
    /* V15 Pro 樣式 */
    .adv-stats-box { background-color: #25262b; padding: 10px; border-radius: 6px; border: 1px solid #444; margin-top: 8px; font-size: 0.75rem; }
    .section-title { font-size: 0.8rem; font-weight: bold; color: #ff9800; border-bottom: 1px solid #444; padding-bottom: 2px; margin-bottom: 5px; margin-top: 5px; }
    .odds-row { display: flex; justify-content: space-between; margin-bottom: 3px; font-size: 0.75rem; }
    .odds-val { color: #fff; font-weight: bold; }
    .odds-val-high { color: #00ff00; font-weight: bold; }
    .value-bet { color: #ff00ff !important; font-weight: 900; animation: blinker 2s infinite; }
    
    .goal-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 4px; margin: 8px 0; text-align: center; }
    .goal-item { background: #333; padding: 4px; border-radius: 4px; border: 1px solid #444; }
    .goal-title { font-size: 0.7rem; color: #aaa; }
    .goal-val { font-size: 0.9rem; font-weight: bold; color: #fff; }
    .highlight-goal { border: 1px solid #28a745 !important; background: rgba(40, 167, 69, 0.2) !important; box-shadow: 0 0 8px rgba(40,167,69,0.4); }
    
    .smart-tag { display: inline-block; background: #444; border-radius: 3px; padding: 1px 5px; font-size: 0.7rem; margin-right: 3px; color: #fff; border: 1px solid #555; }
    .risk-badge { font-weight: bold; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; color:#fff; }
    .risk-low { background-color: #28a745; border: 1px solid #1e7e34; }
    .risk-med { background-color: #17a2b8; border: 1px solid #117a8b; }
    .risk-high { background-color: #dc3545; border: 1px solid #bd2130; }
    
    .top-pick-box { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 10px; border-radius: 6px; text-align: center; margin-bottom: 8px; border: 1px solid #8e44ad; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    .top-pick-title { font-size: 0.75rem; color: #eee; font-weight:bold; letter-spacing: 1px; }
    .top-pick-val { font-size: 1.3rem; font-weight: 900; color: #fff; text-shadow: 0 2px 4px rgba(0,0,0,0.5); margin-top: 2px; }
    
    .min-odds-box { border: 1px dashed #666; padding: 2px 5px; border-radius: 3px; color: #aaa; font-size: 0.7rem; margin-top: 2px; }
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
    st.title("⚽ 足球AI Alpha Pro (V15.0)")
    
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
    num_cols = ['主預測', '客預測', '主攻(H)', '客攻(A)', '賽事風格', '主動量', '客動量', 'BTTS', '主零封', '客零封', '大球率1.5', '大球率2.5', '大球率3.5', 'OU信心', 'H2H平均球', '合理主賠', '合理和賠', '合理客賠', '合理大賠2.5', '合理細賠2.5', '上半大0.5', '最低賠率主', '最低賠率客']
    for col in num_cols: 
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    st.sidebar.header("🔍 篩選條件")
    leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
    selected_league = st.sidebar.selectbox("選擇聯賽:", leagues)
    
    df['日期'] = df['時間'].apply(lambda x: str(x).split(' ')[0])
    available_dates = ["全部"] + sorted(list(set(df['日期'])))
    selected_date = st.sidebar.selectbox("📅 選擇日期:", available_dates
