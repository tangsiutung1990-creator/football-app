import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import time

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 
CSV_FILENAME = "football_data_backup.csv" 

st.set_page_config(page_title="足球AI Pro (V39.2 Full)", page_icon="⚽", layout="wide")

# ================= CSS (HTML 修復與優化) =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    [data-testid="stSidebar"] { background-color: #161b22; min-width: 220px; }
    
    .compact-card { 
        background-color: #1e222d; 
        border: 1px solid #30363d; 
        border-radius: 10px; 
        padding: 12px; 
        margin-bottom: 12px; 
        font-family: sans-serif;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    .match-header { display: flex; justify-content: space-between; color: #8b949e; font-size: 0.8rem; margin-bottom: 8px; border-bottom: 1px solid #333; padding-bottom: 5px; }
    .status-live { color: #ff5252; font-weight: bold; animation: pulse 1.5s infinite; }
    
    .team-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
    .team-name { font-weight: bold; font-size: 1.1rem; color: #e6edf3; display: flex; align-items: center; gap: 6px; } 
    .score { font-weight: bold; font-size: 1.2rem; color: #58a6ff; }
    
    .rank-badge { background: #333; color: #aaa; font-size: 0.7rem; padding: 2px 5px; border-radius: 4px; }
    
    /* 賠率與數據網格 - 4欄佈局 */
    .data-grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 4px; margin-top: 10px; background: #0d1117; padding: 6px; border-radius: 6px; }
    .grid-col { text-align: center; border-right: 1px solid #30363d; }
    .grid-col:last-child { border-right: none; }
    
    .grid-title { color: #8b949e; font-size: 0.7rem; margin-bottom: 2px; font-weight: bold; display: block; }
    .grid-val { color: #fff; font-size: 0.85rem; font-weight: bold; }
    .val-green { color: #3fb950; }
    .val-blue { color: #58a6ff; }
    
    /* Value Bet 標籤 */
    .money-icon { color: #ffd700; font-size: 1rem; margin-left: 4px; }
    
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.6; } 100% { opacity: 1; } }
</style>
""", unsafe_allow_html=True)

# ================= 數據加載與防崩潰 =================
@st.cache_data(ttl=300)
def load_data():
    df = pd.DataFrame()
    src = "無"
    
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        # 判斷環境變數或本地 Key
        if "gcp_service_account" in st.secrets:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        elif os.path.exists("key.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        else: return pd.DataFrame(), "無 Key"

        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        src = "Google Cloud"
    except:
        if os.path.exists(CSV_FILENAME):
            df = pd.read_csv(CSV_FILENAME)
            src = "Local CSV"
            
    # 【自動補全欄位】防止 KeyError
    required_cols = [
        '聯賽','時間','狀態','主隊','客隊','主分','客分',
        '主勝率','客勝率','大2.5','BTTS',
        '主賠','和賠','客賠','亞盤主','亞盤客','球頭','大球','小球',
        '主Value','客Value','xG主','xG客','主排名','客排名'
    ]
    if df.empty: df = pd.DataFrame(columns=required_cols)
    for c in required_cols:
        if c not in df.columns: df[c] = ""
        
    return df, src

def safe_fmt(val):
    try:
        if val == "" or val is None: return "-"
        f = float(str(val).replace('%',''))
        return f"{f:.2f}" if f > 0 else "-"
    except: return "-"

def safe_int(val):
    try: return int(float(str(val).replace('%','')))
    except: return 0

# ================= 主程式 =================
def main():
    st.title("⚽ 足球AI Pro (V39.2 Full)")
    
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
        st.rerun()
        
    df, source = load_data()

    if df.empty:
        st.warning(f"⚠️ 數據庫為空 (來源: {source})。請等待 run_me.py 運行。")
        return

    # 側邊欄篩選
    with st.sidebar:
        st.header("🔍 篩選")
        leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
        sel_lg = st.selectbox("聯賽:", leagues)
        status_opts = ["全部", "未開賽", "進行中", "完場"]
        sel_status = st.radio("狀態:", status_opts)
        
        if sel_lg != "全部": df = df[df['聯賽'] == sel_lg]
        if sel_status != "全部": df = df[df['狀態'] == sel_status]

    st.caption(f"數據來源: {source} | 場次: {len(df)}")

    # 排序
    df['sort'] = df['狀態'].apply(lambda x: 0 if x=="進行中" else 1 if x=="未開賽" else 2)
    df = df.sort_values(by=['sort', '時間'])

    # 卡片渲染 (注意：HTML 字串完全靠左，防止縮排變代碼)
    for idx, row in df.iterrows():
        s_cls = "status-live" if row['狀態'] == "進行中" else ""
        
        # 數據清洗
        ph = safe_int(row.get('主勝率')); pa = safe_int(row.get('客勝率'))
        po = safe_int(row.get('大2.5'))
        
        odd_h = safe_fmt(row.get('主賠')); odd_d = safe_fmt(row.get('和賠')); odd_a = safe_fmt(row.get('客賠'))
        ah_h = safe_fmt(row.get('亞盤主')); ah_a = safe_fmt(row.get('亞盤客'))
        ou_line = str(row.get('球頭', '2.5'))
        ou_o = safe_fmt(row.get('大球')); ou_u = safe_fmt(row.get('小球'))
        
        icon_h = "💰" if str(row.get('主Value')) == "💰" else ""
        icon_a = "💰" if str(row.get('客Value')) == "💰" else ""

        # HTML 構造 (無縮排)
        html = f"""
<div class="compact-card">
<div class="match-header">
<span>{row.get('時間','')} | {row.get('聯賽','')}</span>
<span class="{s_cls}">{row.get('狀態','')}</span>
</div>
<div class="team-row">
<div class="team-name">{row.get('主隊','')} <span class="rank-badge">#{row.get('主排名','-')}</span> {icon_h}</div>
<div class="score">{row.get('主分','')}</div>
</div>
<div class="team-row">
<div class="team-name">{row.get('客隊','')} <span class="rank-badge">#{row.get('客排名','-')}</span> {icon_a}</div>
<div class="score">{row.get('客分','')}</div>
</div>
<div class="data-grid">
<div class="grid-col">
<span class="grid-title">勝率 (AI)</span>
<div class="grid-val">{ph}% / {pa}%</div>
</div>
<div class="grid-col">
<span class="grid-title">獨贏 (1x2)</span>
<div class="grid-val val-blue">{odd_h} | {odd_a}</div>
</div>
<div class="grid-col">
<span class="grid-title">亞盤</span>
<div class="grid-val">{ah_h} | {ah_a}</div>
</div>
<div class="grid-col">
<span class="grid-title">大小 ({ou_line})</span>
<div class="grid-val">{ou_o} | {ou_u}</div>
</div>
</div>
<div style="text-align:right; font-size:0.7rem; color:#666; margin-top:4px;">
xG: {row.get('xG主','-')} - {row.get('xG客','-')} | 大2.5: {po}%
</div>
</div>
"""
        st.markdown(html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
