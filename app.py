import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import time

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI Pro (V38.1 Fix)", page_icon="⚽", layout="wide")

# ================= CSS (暗黑修復版) =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    [data-testid="stSidebar"] { background-color: #161b22; }
    
    .compact-card { 
        background-color: #1e222d; 
        border: 1px solid #30363d; 
        border-radius: 8px; 
        padding: 12px; 
        margin-bottom: 10px; 
        font-family: sans-serif;
    }
    
    .match-header { display: flex; justify-content: space-between; color: #8b949e; font-size: 0.8rem; margin-bottom: 8px; border-bottom: 1px solid #333; padding-bottom: 5px; }
    .status-live { color: #ff5252; font-weight: bold; }
    
    .content-row { display: grid; grid-template-columns: 7fr 3fr; align-items: center; }
    
    .team-name { font-weight: bold; font-size: 1.1rem; color: #e6edf3; margin-bottom: 5px; } 
    .rank-badge { background: #333; color: #aaa; font-size: 0.7rem; padding: 2px 5px; border-radius: 4px; margin-left: 5px; }
    
    .score-main { font-size: 1.8rem; font-weight: bold; color: #58a6ff; text-align: right; }
    .xg-sub { font-size: 0.75rem; color: #888; text-align: right; display: block; }
    
    .grid-matrix { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5px; margin-top: 10px; background: #111; padding: 5px; border-radius: 5px; text-align: center; }
    .matrix-header { color: #888; font-size: 0.7rem; }
    .cell-val { color: #fff; font-weight: bold; font-size: 0.9rem; }
    .val-highlight { color: #00e676; }
</style>
""", unsafe_allow_html=True)

# ================= 數據讀取 (含自動修復) =================
@st.cache_data(ttl=300)
def load_data():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    df = pd.DataFrame()
    src = "無"
    
    try:
        # 嘗試讀取 Google Sheet
        if "gcp_service_account" in st.secrets:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        elif os.path.exists("key.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        else:
            return pd.DataFrame(), "無 Key"

        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        src = "Google Cloud"
    except:
        # 失敗則讀取 CSV
        if os.path.exists("football_data_backup.csv"):
            df = pd.read_csv("football_data_backup.csv")
            src = "Backup CSV"
            
    # 【關鍵修復】補全缺失欄位，防止 KeyError
    required_cols = ['聯賽','時間','狀態','主隊','客隊','主分','客分','xG主','xG客',
                     '主胜率','客胜率','大2.5','BTTS','主賠','客賠','主Value','客Value',
                     '主排名','客排名','主走勢','客走勢']
    
    if not df.empty:
        for col in required_cols:
            if col not in df.columns:
                df[col] = "" # 補上空值
                
    return df, src

# ================= 主程式 =================
def main():
    st.title("⚽ 足球AI Pro (V38.1 Live)")
    
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
        st.rerun()
        
    df, source = load_data()
    
    if df.empty:
        st.warning(f"⚠️ 暫無數據 (來源: {source})。請等待 run_me.py 更新。")
        return

    # 排序
    df['sort'] = df['狀態'].apply(lambda x: 0 if x in ['LIVE','1H','2H','HT'] else 1 if x=='NS' else 2)
    df = df.sort_values(by=['sort', '時間'])

    # 側邊欄
    leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
    sel_lg = st.sidebar.selectbox("聯賽", leagues)
    if sel_lg != "全部": df = df[df['聯賽'] == sel_lg]
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("💎 推薦")
    # 安全過濾，防止報錯
    try:
        val_bets = df[ (df['主Value'].astype(str)=='💰') | (df['客Value'].astype(str)=='💰') ]
        for _, r in val_bets.iterrows():
            pick = r['主隊'] if str(r['主Value'])=='💰' else r['客隊']
            st.sidebar.markdown(f"{r['聯賽']} {pick}")
    except: pass

    st.caption(f"數據來源: {source} | 場次: {len(df)}")

    # 卡片顯示
    for idx, row in df.iterrows():
        # 數據清洗
        ph = row.get('主胜率',0); pa = row.get('客胜率',0)
        po = row.get('大2.5',0); pb = row.get('BTTS',0)
        status_cls = "status-live" if row['狀態'] in ['LIVE','1H','2H','HT'] else ""
        
        # 【關鍵修復】HTML 字串頂格寫，不要縮排，防止被當成代碼顯示
        card_html = f"""
<div class="compact-card">
<div class="match-header">
<span>{row.get('時間','')} | {row.get('聯賽','')}</span>
<span class="{status_cls}">{row.get('狀態','')}</span>
</div>
<div class="content-row">
<div>
<div class="team-name">{row.get('主隊','')} <span class="rank-badge">#{row.get('主排名','-')}</span> {row.get('主Value','')}</div>
<div class="team-name">{row.get('客隊','')} <span class="rank-badge">#{row.get('客排名','-')}</span> {row.get('客Value','')}</div>
</div>
<div style="text-align:right;">
<div class="score-main">{row.get('主分','')} - {row.get('客分','')}</div>
<span class="xg-sub">xG: {row.get('xG主','')} - {row.get('xG客','')}</span>
</div>
</div>
<div class="grid-matrix">
<div><div class="matrix-header">主勝率</div><div class="cell-val { 'val-highlight' if float(str(ph).replace('%',''))>50 else ''}">{ph}%</div></div>
<div><div class="matrix-header">客勝率</div><div class="cell-val { 'val-highlight' if float(str(pa).replace('%',''))>50 else ''}">{pa}%</div></div>
<div><div class="matrix-header">大2.5</div><div class="cell-val { 'val-highlight' if float(str(po).replace('%',''))>55 else ''}">{po}%</div></div>
<div><div class="matrix-header">賠率</div><div class="cell-val" style="color:#58a6ff">{row.get('主賠','-')} | {row.get('客賠','-')}</div></div>
</div>
</div>
"""
        st.markdown(card_html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
