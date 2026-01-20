import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import time

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI Pro (V39.0 Full)", page_icon="⚽", layout="wide")

# ================= CSS (佈局優化) =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    [data-testid="stSidebar"] { background-color: #161b22; }
    
    .compact-card { 
        background-color: #1e222d; 
        border: 1px solid #30363d; 
        border-radius: 8px; 
        padding: 15px; 
        margin-bottom: 15px; 
        font-family: sans-serif;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
    }
    
    .match-header { display: flex; justify-content: space-between; color: #8b949e; font-size: 0.85rem; border-bottom: 1px solid #333; padding-bottom: 8px; margin-bottom: 10px; }
    .status-live { color: #ff5252; font-weight: bold; animation: pulse 1.5s infinite; }
    
    .team-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; }
    .team-name { font-weight: bold; font-size: 1.2rem; color: #e6edf3; }
    .score { font-weight: bold; font-size: 1.2rem; color: #58a6ff; }
    
    /* 賠率網格 - 改為 3 欄 (獨贏, 亞盤, 大小) */
    .odds-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-top: 12px; background: #0d1117; padding: 8px; border-radius: 6px; }
    .odds-col { text-align: center; border-right: 1px solid #30363d; }
    .odds-col:last-child { border-right: none; }
    
    .odds-title { color: #8b949e; font-size: 0.75rem; margin-bottom: 4px; display: block; }
    .odds-val { color: #3fb950; font-weight: bold; font-size: 0.95rem; }
    .odds-label { color: #aaa; font-size: 0.8rem; margin-right: 4px; }
    
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.6; } 100% { opacity: 1; } }
</style>
""", unsafe_allow_html=True)

# ================= 數據讀取 =================
@st.cache_data(ttl=300)
def load_data():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    df = pd.DataFrame()
    src = "無"
    
    try:
        # 1. 嘗試 Google Sheet
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
        # 2. 備份 CSV
        if os.path.exists("football_data_backup.csv"):
            df = pd.read_csv("football_data_backup.csv")
            src = "Local CSV"
    
    # 【自動補欄位】確保 app 不會崩潰
    required = ['聯賽','時間','狀態','主隊','客隊','主分','客分',
                '主勝','和局','客勝','亞盤主','亞盤客','球頭','大球','小球']
    if df.empty: df = pd.DataFrame(columns=required)
    for c in required:
        if c not in df.columns: df[c] = ""
        
    return df, src

def safe_fmt(val):
    try:
        f = float(val)
        return f"{f:.2f}" if f > 0 else "-"
    except: return "-"

# ================= 主程式 =================
def main():
    st.title("⚽ 足球AI Pro (V39.0 全盤口版)")
    
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
        st.rerun()
        
    df, source = load_data()
    
    if df.empty:
        st.warning("⚠️ 暫無數據，請先運行 run_me.py")
        return

    # 側邊欄篩選 (恢復詳細篩選)
    with st.sidebar:
        st.header("🔍 篩選")
        
        # 狀態篩選
        status_opts = ["全部", "未開賽", "進行中", "完場", "取消/延遲"]
        sel_status = st.radio("比賽狀態:", status_opts)
        
        # 聯賽篩選
        leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
        sel_lg = st.selectbox("聯賽:", leagues)
        
        # 應用篩選
        if sel_status == "未開賽": df = df[df['狀態'] == "未開賽"]
        elif sel_status == "進行中": df = df[df['狀態'] == "進行中"]
        elif sel_status == "完場": df = df[df['狀態'] == "完場"]
        elif sel_status == "取消/延遲": df = df[df['狀態'].isin(["取消/延遲", "PST", "CANC", "ABD"])]
        
        if sel_lg != "全部": df = df[df['聯賽'] == sel_lg]

    st.caption(f"數據來源: {source} | 顯示場次: {len(df)}")

    # 排序：進行中優先
    df['sort'] = df['狀態'].apply(lambda x: 0 if x=="進行中" else 1 if x=="未開賽" else 2)
    df = df.sort_values(by=['sort', '時間'])

    # 卡片渲染
    for idx, row in df.iterrows():
        s_cls = "status-live" if row['狀態'] == "進行中" else ""
        
        # 賠率格式化
        odd_h = safe_fmt(row.get('主勝')); odd_d = safe_fmt(row.get('和局')); odd_a = safe_fmt(row.get('客勝'))
        ah_h = safe_fmt(row.get('亞盤主')); ah_a = safe_fmt(row.get('亞盤客'))
        ou_line = str(row.get('球頭', '2.5'))
        ou_o = safe_fmt(row.get('大球')); ou_u = safe_fmt(row.get('小球'))

        html = f"""
<div class="compact-card">
    <div class="match-header">
        <span>{row.get('時間','')} | {row.get('聯賽','')}</span>
        <span class="{s_cls}">{row.get('狀態','')}</span>
    </div>
    
    <div class="team-row">
        <span class="team-name">{row.get('主隊','')}</span>
        <span class="score">{row.get('主分','')}</span>
    </div>
    <div class="team-row">
        <span class="team-name">{row.get('客隊','')}</span>
        <span class="score">{row.get('客分','')}</span>
    </div>
    
    <div class="odds-grid">
        <div class="odds-col">
            <span class="odds-title">獨贏 (1x2)</span>
            <div><span class="odds-label">主</span><span class="odds-val">{odd_h}</span></div>
            <div><span class="odds-label">和</span><span class="odds-val">{odd_d}</span></div>
            <div><span class="odds-label">客</span><span class="odds-val">{odd_a}</span></div>
        </div>
        <div class="odds-col">
            <span class="odds-title">亞盤 (Handicap)</span>
            <div><span class="odds-label">主</span><span class="odds-val">{ah_h}</span></div>
            <div><span class="odds-label">客</span><span class="odds-val">{ah_a}</span></div>
        </div>
        <div class="odds-col">
            <span class="odds-title">大小 (O/U {ou_line})</span>
            <div><span class="odds-label">大</span><span class="odds-val">{ou_o}</span></div>
            <div><span class="odds-label">小</span><span class="odds-val">{ou_u}</span></div>
        </div>
    </div>
</div>
"""
        st.markdown(html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
