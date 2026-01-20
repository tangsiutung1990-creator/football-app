import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from datetime import datetime

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 
CSV_FILENAME = "football_data_backup.csv" 

st.set_page_config(page_title="足球AI Pro (V40.8 Debug)", page_icon="⚽", layout="wide")

# ================= CSS =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    [data-testid="stSidebar"] { min-width: 240px !important; }
    .compact-card { background-color: #1a1c24; border: 1px solid #333; border-radius: 8px; padding: 12px; margin-bottom: 12px; font-family: 'Arial', sans-serif; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    .match-header { display: flex; justify-content: space-between; color: #aaa; font-size: 0.8rem; border-bottom: 1px solid #444; padding-bottom: 5px; margin-bottom: 8px; }
    .status-live { color: #ff5252; font-weight: bold; animation: pulse 1.5s infinite; }
    .status-fin { color: #aaa; }
    .team-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
    .team-name { font-weight: bold; font-size: 1.1rem; color: #fff; display: flex; align-items: center; gap: 5px; }
    .score { font-size: 1.2rem; font-weight: bold; color: #00e5ff; }
    .grid-box { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; margin-top: 10px; background: #111; padding: 5px; border-radius: 5px; }
    .grid-item { text-align: center; border-right: 1px solid #333; }
    .grid-item:last-child { border-right: none; }
    .grid-label { font-size: 0.7rem; color: #888; display: block; }
    .grid-val { font-size: 0.85rem; color: #eee; font-weight: bold; }
    .high-val { color: #00e676; }
    .ah-box { background: #222; padding: 4px; border-radius: 4px; margin-top: 5px; display: flex; justify-content: space-around; font-size: 0.8rem; color: #ccc; }
    .ah-val { color: #ffd700; font-weight: bold; }
    .ou-table { width: 100%; font-size: 0.75rem; color: #ccc; margin-top: 5px; border-collapse: collapse; }
    .ou-table td { border: 1px solid #333; padding: 2px 4px; text-align: center; }
    .ou-head { background: #333; font-weight: bold; color: #fff; }
    .val-badge { background: #ffd700; color: #000; padding: 1px 4px; border-radius: 3px; font-size: 0.7rem; font-weight: bold; }
    .rank-badge { background: #444; color: #fff; padding: 1px 4px; border-radius: 3px; font-size: 0.7rem; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.6; } 100% { opacity: 1; } }
</style>
""", unsafe_allow_html=True)

# ================= 數據加載 (底層重構: 使用 get_all_values) =================
# ttl=0 確保每次都從 Google Sheet 拉最新數據，不緩存
@st.cache_data(ttl=0)
def load_data():
    df = pd.DataFrame()
    src = "無"
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        if "gcp_service_account" in st.secrets:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        
        # 【核心修改】直接抓取所有原始值，這是最穩定的方法
        raw_data = sheet.get_all_values()
        if raw_data and len(raw_data) > 1:
            headers = raw_data[0]
            rows = raw_data[1:]
            df = pd.DataFrame(rows, columns=headers)
            src = "Cloud"
    except:
        if os.path.exists(CSV_FILENAME):
            df = pd.read_csv(CSV_FILENAME)
            src = "Local"
            
    # 補全欄位
    req = [
        '聯賽','時間','狀態','主隊','客隊','主分','客分','xG主','xG客',
        '主勝率','和率','客勝率','主Value','和Value','客Value',
        '全場大0.5','全場大1.5','全場大2.5','全場大3.5','半場大0.5','半場大1.5',
        'BTTS機率','主先入球率','亞盤主','亞盤客','亞盤盤口', '主排名', '客排名', '數據源',
        '主賠', '和賠', '客賠'
    ]
    
    if df.empty:
        df = pd.DataFrame(columns=req)
    else:
        for c in req:
            if c not in df.columns: df[c] = ""
            
    return df, src

def safe_fmt(val, is_pct=False):
    try:
        if val is None: return "-"
        s = str(val).strip()
        if s == "" or s.lower() == "nan" or s == "-": return "-"
        f = float(s.replace('%',''))
        if f == 0: return "-"
        if is_pct: return f"{int(f)}%"
        return f"{f:.2f}"
    except: return "-"

def get_cls(val):
    try:
        if val is None: return ""
        s = str(val).replace('%','').replace('-','0').strip()
        if not s: return ""
        v = float(s)
        return 'high-val' if v > 50 else ''
    except: return ""

# ================= 主程式 =================
def main():
    st.title("⚽ 足球AI Pro (V40.8 Debug)")
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🗑️ 清除緩存"):
            st.cache_data.clear()
            st.rerun()
    with col2:
        if st.button("🔄 刷新數據"):
            st.rerun()

    df, src = load_data()
    if df.empty:
        st.warning(f"⚠️ 暫無數據 (來源: {src})")
        return

    with st.sidebar:
        st.header("🔍 篩選")
        # 顯示原始數據開關
        show_raw = st.checkbox("🐞 顯示原始數據 (Debug)")
        
        status_list = ["全部", "未開賽", "進行中", "完場", "取消/延期"]
        sel_status = st.selectbox("狀態", status_list)
        
        sel_date = None
        if sel_status == "完場":
            st.info("📅 請選擇完場日期")
            try:
                unique_dates = sorted(list(set(df['時間'].astype(str).str[:10])))
                if unique_dates:
                    sel_date = st.selectbox("日期", unique_dates, index=len(unique_dates)-1)
                else:
                    sel_date = st.date_input("日期", datetime.now())
            except:
                sel_date = st.date_input("日期", datetime.now())
            
        leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
        sel_lg = st.selectbox("聯賽", leagues)

        if sel_status != "全部":
            if sel_status == "取消/延期":
                df = df[df['狀態'].astype(str).str.contains("取消|延期", na=False)]
            elif sel_status == "完場":
                df = df[df['狀態'] == "完場"]
                if sel_date:
                    df = df[df['時間'].astype(str).str.startswith(str(sel_date), na=False)]
            else:
                df = df[df['狀態'] == sel_status]
        if sel_lg != "全部": df = df[df['聯賽'] == sel_lg]

    # === Debug 顯示 ===
    if show_raw:
        st.subheader("📊 原始數據表 (Debug Mode)")
        st.dataframe(df)

    st.caption(f"來源: {src} | 共 {len(df)} 場")

    try:
        df['sort'] = df['狀態'].apply(lambda x: 0 if str(x)=="進行中" else 1 if str(x)=="未開賽" else 2)
        df = df.sort_values(by=['sort', '時間'])
    except: pass

    for idx, row in df.iterrows():
        ph = safe_fmt(row.get('主勝率'), True)
        pd_prob = safe_fmt(row.get('和率'), True)
        pa = safe_fmt(row.get('客勝率'), True)
        val_h = "<span class='val-badge'>💰</span>" if str(row.get('主Value'))=='💰' else ""
        val_d = "<span class='val-badge'>💰</span>" if str(row.get('和Value'))=='💰' else ""
        val_a = "<span class='val-badge'>💰</span>" if str(row.get('客Value'))=='💰' else ""
        ah_line = str(row.get('亞盤盤口')) if row.get('亞盤盤口') else '平手'
        s_cls = 'status-live' if str(row.get('狀態'))=='進行中' else 'status-fin'
        
        # HTML 結構 (確保無縮排)
        html = f"""
<div class="compact-card">
<div class="match-header">
<span>{row.get('時間','-')} | {row.get('聯賽','-')}</span>
<span class="{s_cls}">{row.get('狀態','-')}</span>
</div>
<div class="team-row">
<span class="team-name">{row.get('主隊','-')} <span class="rank-badge">#{row.get('主排名','-')}</span> {val_h}</span>
<span class="score">{row.get('主分','')}</span>
</div>
<div class="team-row">
<span class="team-name">{row.get('客隊','-')} <span class="rank-badge">#{row.get('客排名','-')}</span> {val_a}</span>
<span class="score">{row.get('客分','')}</span>
</div>
<div class="grid-box">
<div class="grid-item"><span class="grid-label">主勝率</span><span class="grid-val {get_cls(ph)}">{ph}</span></div>
<div class="grid-item"><span class="grid-label">和率</span><span class="grid-val">{pd_prob} {val_d}</span></div>
<div class="grid-item"><span class="grid-label">客勝率</span><span class="grid-val {get_cls(pa)}">{pa}</span></div>
<div class="grid-item"><span class="grid-label">BTTS</span><span class="grid-val">{safe_fmt(row.get('BTTS機率'), True)}</span></div>
<div class="grid-item"><span class="grid-label">主先入</span><span class="grid-val">{safe_fmt(row.get('主先入球率'), True)}</span></div>
</div>
<div class="ah-box">
<span>亞盤主: <span class="ah-val">{safe_fmt(row.get('亞盤主'))}</span></span>
<span>盤口: <span style="color:#fff">{ah_line}</span></span>
<span>亞盤客: <span class="ah-val">{safe_fmt(row.get('亞盤客'))}</span></span>
</div>
<table class="ou-table">
<tr class="ou-head"><td>盤口</td><td>0.5</td><td>1.5</td><td>2.5</td><td>3.5</td></tr>
<tr><td>全場大</td><td>{safe_fmt(row.get('全場大0.5'))}</td><td>{safe_fmt(row.get('全場大1.5'))}</td><td>{safe_fmt(row.get('全場大2.5'))}</td><td>{safe_fmt(row.get('全場大3.5'))}</td></tr>
<tr><td>半場大</td><td>{safe_fmt(row.get('半場大0.5'))}</td><td>{safe_fmt(row.get('半場大1.5'))}</td><td colspan="2" style="color:#555">-</td></tr>
</table>
<div style="text-align:right; font-size:0.7rem; color:#666; margin-top:5px;">xG: {row.get('xG主','-')} - {row.get('xG客','-')} (源:{row.get('數據源','-')})</div>
</div>
"""
        st.markdown(html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
