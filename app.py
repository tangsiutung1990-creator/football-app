import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import time

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI Pro (V38.1 Final)", page_icon="⚽", layout="wide")

# ================= CSS 樣式 =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    [data-testid="stSidebar"] { background-color: #161b22; }
    
    /* 卡片樣式 */
    .compact-card { 
        background-color: #1e222d; 
        border: 1px solid #30363d; 
        border-radius: 8px; 
        padding: 12px; 
        margin-bottom: 10px; 
        font-family: sans-serif;
    }
    
    .match-header { display: flex; justify-content: space-between; color: #8b949e; font-size: 0.8rem; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 8px; }
    .status-live { color: #ff5252; font-weight: bold; }
    
    .content-row { display: grid; grid-template-columns: 7fr 3fr; align-items: center; }
    
    .team-name { font-weight: bold; font-size: 1.1rem; color: #e6edf3; margin-bottom: 5px; display: flex; align-items: center; } 
    .rank-badge { background: #333; color: #aaa; font-size: 0.7rem; padding: 2px 5px; border-radius: 4px; margin-left: 5px; font-weight: normal; }
    
    .score-area { text-align: right; }
    .score-main { font-size: 1.8rem; font-weight: bold; color: #58a6ff; line-height: 1.2; }
    .xg-sub { font-size: 0.75rem; color: #888; display: block; }
    
    .grid-matrix { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5px; margin-top: 10px; background: #111; padding: 5px; border-radius: 5px; text-align: center; }
    .matrix-header { color: #888; font-size: 0.7rem; margin-bottom: 2px; }
    .cell-val { color: #fff; font-weight: bold; font-size: 0.9rem; }
    
    /* 高亮樣式 */
    .val-highlight { color: #00e676; }
    .money-icon { color: #ffd700; margin-left: 5px; font-size: 1rem; }
</style>
""", unsafe_allow_html=True)

# ================= 數據讀取與防崩潰機制 =================
@st.cache_data(ttl=300)
def load_data():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    df = pd.DataFrame()
    src = "無"
    
    try:
        # 1. 嘗試連線 Google Sheet
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
        # 2. 失敗則讀取 CSV 備份
        if os.path.exists("football_data_backup.csv"):
            df = pd.read_csv("football_data_backup.csv")
            src = "Local CSV"
            
    # 【關鍵修復 1】補全缺失欄位，防止 KeyError
    required_cols = ['聯賽','時間','狀態','主隊','客隊','主分','客分','xG主','xG客',
                     '主胜率','客胜率','大2.5','BTTS','主賠','客賠','主Value','客Value',
                     '主排名','客排名','主走勢','客走勢']
    
    # 如果 DataFrame 是空的，先創建立一個帶有表頭的空表
    if df.empty:
        df = pd.DataFrame(columns=required_cols)
    else:
        # 檢查每一個欄位，如果沒有就補上空字串
        for col in required_cols:
            if col not in df.columns:
                df[col] = "" 
                
    return df, src

# 【關鍵修復 2】安全的數值轉換，防止 ValueError
def safe_parse(val):
    try:
        # 移除 % 並轉為 float
        return float(str(val).replace('%', ''))
    except:
        return 0.0

# ================= 主程式 =================
def main():
    st.title("⚽ 足球AI Pro (V38.1 Final)")
    
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
        st.rerun()
        
    df, source = load_data()
    
    if df.empty:
        st.warning(f"⚠️ 暫無數據 (來源: {source})。請確認 run_me.py 是否已運行。")
        return

    # 排序：進行中 > 未開賽 > 完場
    try:
        df['sort'] = df['狀態'].apply(lambda x: 0 if x in ['LIVE','1H','2H','HT'] else 1 if x=='NS' else 2)
        df = df.sort_values(by=['sort', '時間'])
    except: pass

    # 側邊欄篩選
    with st.sidebar:
        leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
        sel_lg = st.selectbox("聯賽", leagues)
        if sel_lg != "全部": df = df[df['聯賽'] == sel_lg]
        
        st.markdown("---")
        st.subheader("💎 價值推薦")
        
        # 使用安全的過濾方式
        try:
            # 確保轉為字串再比較，防止類型錯誤
            val_bets = df[ (df['主Value'].astype(str).str.contains('💰')) | (df['客Value'].astype(str).str.contains('💰')) ]
            if not val_bets.empty:
                for _, r in val_bets.iterrows():
                    pick = r['主隊'] if '💰' in str(r['主Value']) else r['客隊']
                    odds = r['主賠'] if '💰' in str(r['主Value']) else r['客賠']
                    st.markdown(f"**{r['聯賽']}**: {pick} @{odds}")
            else:
                st.markdown("暫無推薦")
        except: 
            st.markdown("數據讀取中...")

    st.caption(f"數據來源: {source} | 場次: {len(df)}")

    # 卡片顯示
    for idx, row in df.iterrows():
        # 數據清洗 (使用 safe_parse 防止報錯)
        ph = safe_parse(row.get('主胜率')); pa = safe_parse(row.get('客胜率'))
        po = safe_parse(row.get('大2.5')); pb = safe_parse(row.get('BTTS'))
        
        status_cls = "status-live" if row['狀態'] in ['LIVE','1H','2H','HT'] else ""
        
        # 判斷是否高亮 (數值 > 50 變綠色)
        cls_h = 'val-highlight' if ph > 50 else ''
        cls_a = 'val-highlight' if pa > 50 else ''
        cls_o = 'val-highlight' if po > 55 else ''
        
        # Value 圖標
        icon_h = '<span class="money-icon">💰</span>' if '💰' in str(row.get('主Value')) else ''
        icon_a = '<span class="money-icon">💰</span>' if '💰' in str(row.get('客Value')) else ''

        # 【關鍵修復 3】HTML 字串完全靠左，移除所有縮排，確保 Streamlit 渲染正確
        card_html = f"""
<div class="compact-card">
<div class="match-header">
<span>{row.get('時間','')} | {row.get('聯賽','')}</span>
<span class="{status_cls}">{row.get('狀態','')}</span>
</div>
<div class="content-row">
<div>
<div class="team-name">{row.get('主隊','')} <span class="rank-badge">#{row.get('主排名','-')}</span> {icon_h}</div>
<div class="team-name">{row.get('客隊','')} <span class="rank-badge">#{row.get('客排名','-')}</span> {icon_a}</div>
</div>
<div class="score-area">
<div class="score-main">{row.get('主分','')} - {row.get('客分','')}</div>
<span class="xg-sub">xG: {row.get('xG主','')} - {row.get('xG客','')}</span>
</div>
</div>
<div class="grid-matrix">
<div><div class="matrix-header">主勝率</div><div class="cell-val {cls_h}">{int(ph)}%</div></div>
<div><div class="matrix-header">客勝率</div><div class="cell-val {cls_a}">{int(pa)}%</div></div>
<div><div class="matrix-header">大2.5</div><div class="cell-val {cls_o}">{int(po)}%</div></div>
<div><div class="matrix-header">賠率</div><div class="cell-val" style="color:#58a6ff">{row.get('主賠','-')} | {row.get('客賠','-')}</div></div>
</div>
</div>
"""
        st.markdown(card_html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
