import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import time

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

# 必須是第一個 Streamlit 命令
st.set_page_config(page_title="足球AI Pro (V38.1 Live)", page_icon="⚽", layout="wide")

# ================= CSS 優化 (暗黑高級質感) =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    [data-testid="stSidebar"] { background-color: #161b22; }
    
    .compact-card { 
        background-color: #1e222d; 
        border: 1px solid #30363d; 
        border-radius: 10px; 
        padding: 12px; 
        margin-bottom: 12px; 
        font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        transition: transform 0.2s;
    }
    .compact-card:hover { border-color: #58a6ff; }
    
    .match-header { display: flex; justify-content: space-between; color: #8b949e; font-size: 0.8rem; margin-bottom: 8px; border-bottom: 1px solid #30363d; padding-bottom: 6px; }
    .status-live { color: #ff5252; font-weight: bold; animation: pulse 2s infinite; }
    
    .content-row { display: grid; grid-template-columns: 7fr 3fr; align-items: center; }
    
    .team-name { font-weight: 700; font-size: 1.1rem; color: #c9d1d9; margin-bottom: 5px; display: flex; align-items: center; gap: 8px; } 
    .rank-badge { background: #30363d; color: #8b949e; font-size: 0.7rem; padding: 1px 6px; border-radius: 4px; border: 1px solid #484f58; }
    
    .score-main { font-size: 1.8rem; font-weight: 800; color: #58a6ff; text-align: right; letter-spacing: 1px; }
    .xg-sub { font-size: 0.75rem; color: #8b949e; text-align: right; display: block; }
    
    /* 數據矩陣 */
    .grid-matrix { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; margin-top: 10px; background: #161b22; padding: 4px; border-radius: 6px; }
    .matrix-col { text-align: center; }
    .matrix-header { color: #8b949e; font-size: 0.7rem; margin-bottom: 2px; }
    .cell-val { color: #e6edf3; font-weight: bold; font-size: 0.9rem; }
    .val-highlight { color: #3fb950; } /* 綠色高亮 */
    
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
</style>
""", unsafe_allow_html=True)

# ================= 數據加載 (緩存10分鐘) =================
@st.cache_data(ttl=600)
def load_data_from_gsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        # 嘗試從 Streamlit Secrets 讀取 (雲端環境)
        if "gcp_service_account" in st.secrets:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        # 嘗試從本地文件讀取 (本地環境)
        elif os.path.exists("key.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        else:
            return None, "未找到 key.json 或 Secrets 設定"

        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # ===【防崩潰修復】===
        # 確保所有關鍵欄位都存在，如果不存在則補上空值
        required_cols = [
            '聯賽', '時間', '狀態', '主隊', '客隊', 
            '主分', '客分', '主排名', '客排名', '主走勢', '客走勢',
            '主Value', '客Value', 'xG主', 'xG客', 
            '主勝率', '客勝率', '大2.5', 'BTTS', '主賠', '客賠'
        ]
        
        if df.empty:
            return pd.DataFrame(columns=required_cols), "數據表為空"

        for col in required_cols:
            if col not in df.columns:
                df[col] = "" # 補上空欄位防止 KeyError
                
        return df, "Google Cloud"
    except Exception as e:
        return None, str(e)

# ================= 輔助顯示函數 =================
def clean_pct(val):
    try: return int(float(str(val).replace('%', '')))
    except: return 0

def format_odds(val):
    try:
        f = float(val)
        return f"{f:.2f}" if f > 1 else "-"
    except: return "-"

def render_form(form_str):
    if not form_str or len(str(form_str)) < 2: return ""
    dots = ""
    for char in str(form_str)[-5:]:
        color = "#3fb950" if char=='W' else "#d29922" if char=='D' else "#f85149"
        dots += f"<span style='color:{color};font-size:1.2rem;line-height:0.5;'>•</span>"
    return dots

# ================= 主程式 =================
def main():
    st.title("⚽ 足球AI Pro (V38.1 Live)")
    
    # 刷新按鈕
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
        st.rerun()

    df, source = load_data_from_gsheet()

    if df is None:
        st.error(f"❌ 無法讀取數據。錯誤詳情: {source}")
        return

    if df.empty:
        st.warning("⚠️ 數據表目前是空的。請等待 `run_me.py` 完成更新。")
        return

    # 數據處理：排序 (進行中 > 未開賽 > 完場)
    try:
        df['sort_idx'] = df['狀態'].apply(lambda x: 0 if '進行中' in str(x) else 1 if '未開賽' in str(x) else 2)
        df = df.sort_values(by=['sort_idx', '時間'])
    except:
        st.warning("⚠️ 狀態排序時發生輕微錯誤，顯示未排序數據。")

    # 側邊欄
    with st.sidebar:
        st.header("🔍 賽事篩選")
        
        # 聯賽篩選 (確保轉為字串避免錯誤)
        leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
        sel_lg = st.selectbox("選擇聯賽", leagues)
        if sel_lg != "全部": df = df[df['聯賽'] == sel_lg]
        
        # 顯示 Value Bet
        st.markdown("---")
        st.subheader("💎 今日精選")
        
        # 【關鍵修復】這裡使用了安全過濾，即使欄位是空的也不會報錯
        try:
            val_bets = df[(df['主Value'].astype(str) == '💰') | (df['客Value'].astype(str) == '💰')]
            
            if not val_bets.empty:
                for _, r in val_bets.iterrows():
                    pick = r['主隊'] if str(r['主Value']) == '💰' else r['客隊']
                    odds = r['主賠'] if str(r['主Value']) == '💰' else r['客賠']
                    st.markdown(f"**{r['聯賽']}**: {pick} @{format_odds(odds)}")
            else:
                st.markdown("暫無高價值推薦")
        except Exception as e:
            st.error(f"篩選推薦時出錯: {e}")

    st.caption(f"數據來源: {source} | 場次: {len(df)} | 更新: {time.strftime('%H:%M:%S')}")

    # 卡片渲染
    for index, row in df.iterrows():
        # 提取與清理數據
        p_h = clean_pct(row.get('主勝率')); p_a = clean_pct(row.get('客勝率'))
        p_o25 = clean_pct(row.get('大2.5')); p_btts = clean_pct(row.get('BTTS'))
        status_cls = "status-live" if "進行中" in str(row['狀態']) else ""
        
        # HTML 結構
        html = f"""
        <div class="compact-card">
            <div class="match-header">
                <span>{row.get('時間','')} | {row.get('聯賽','')}</span>
                <span class="{status_cls}">{row.get('狀態','')}</span>
            </div>
            <div class="content-row">
                <div>
                    <div class="team-name">
                        {row.get('主隊','')} <span class="rank-badge">#{row.get('主排名','-')}</span>
                        {render_form(row.get('主走勢'))}
                        {'<span style="color:#ffd700">💰</span>' if str(row.get('主Value'))=='💰' else ''}
                    </div>
                    <div class="team-name">
                        {row.get('客隊','')} <span class="rank-badge">#{row.get('客排名','-')}</span>
                        {render_form(row.get('客走勢'))}
                        {'<span style="color:#ffd700">💰</span>' if str(row.get('客Value'))=='💰' else ''}
                    </div>
                </div>
                <div style="text-align:right;">
                    <div class="score-main">{row.get('主分','')} - {row.get('客分','')}</div>
                    <span class="xg-sub">xG: {row.get('xG主',0)} - {row.get('xG客',0)}</span>
                </div>
            </div>
            
            <div class="grid-matrix">
                <div class="matrix-col">
                    <div class="matrix-header">勝率%</div>
                    <div><span class="cell-val { 'val-highlight' if p_h>50 else ''}">{p_h}</span> / <span class="cell-val { 'val-highlight' if p_a>50 else ''}">{p_a}</span></div>
                </div>
                <div class="matrix-col">
                    <div class="matrix-header">進球%</div>
                    <div>大2.5: <span class="cell-val { 'val-highlight' if p_o25>55 else ''}">{p_o25}</span></div>
                </div>
                <div class="matrix-col">
                    <div class="matrix-header">兩隊進球</div>
                    <div>BTTS: <span class="cell-val { 'val-highlight' if p_btts>55 else ''}">{p_btts}</span></div>
                </div>
                <div class="matrix-col">
                    <div class="matrix-header">賠率</div>
                    <div class="cell-val" style="color:#58a6ff">{format_odds(row.get('主賠'))} | {format_odds(row.get('客賠'))}</div>
                </div>
            </div>
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
