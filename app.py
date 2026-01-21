import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from datetime import datetime, timedelta
import pytz

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 
CSV_FILENAME = "football_data_backup.csv" 

st.set_page_config(page_title="足球AI Pro (精選版)", page_icon="⚽", layout="wide")

# ================= CSS 優化 (字體放大 + 空間收窄) =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    
    /* 縮小 Sidebar 頂部空白 */
    .css-1d391kg { padding-top: 1rem; }
    
    .compact-card { 
        background-color: #1a1c24; 
        border: 1px solid #333; 
        border-radius: 8px; 
        padding: 5px 10px; /* 減少上下內邊距 */
        margin-bottom: 8px; /* 減少卡片間距 */
        font-family: 'Arial', sans-serif; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.2); 
    }
    
    .match-header { 
        display: flex; 
        justify-content: space-between; 
        color: #aaa; 
        font-size: 0.85rem; /* 字體加大 */
        margin-bottom: 4px; 
        border-bottom: 1px solid #333; 
        padding-bottom: 2px; 
    }
    
    .content-row { 
        display: grid; 
        grid-template-columns: 6fr 4fr; 
        align-items: center; 
        margin-bottom: 6px; 
    }
    
    .teams-area { text-align: left; }
    
    .team-name { 
        font-weight: bold; 
        font-size: 1.2rem; /* 隊名字體加大 */
        color: #fff; 
        margin-bottom: 2px; 
        display: flex; 
        align-items: center; 
        gap: 6px; 
    } 
    
    .team-sub { 
        font-size: 0.85rem; /* 副標題加大 */
        color: #bbb; 
        display: flex; 
        gap: 8px; 
        align-items: center; 
    }
    
    .rank-badge { 
        background: #444; 
        color: #eee; 
        font-size: 0.75rem; 
        padding: 1px 5px; 
        border-radius: 3px; 
    }
    
    .score-area { text-align: right; }
    .score-main { font-size: 2.0rem; font-weight: bold; color: #00ffea; line-height: 1.1; }
    .score-sub { font-size: 0.8rem; color: #888; }

    /* 網格矩陣優化：字體大、間距小 */
    .grid-matrix { 
        display: grid; 
        grid-template-columns: repeat(4, 1fr); 
        gap: 1px; /* 極窄間距 */
        font-size: 0.85rem; /* 數據字體加大 */
        margin-top: 4px; 
        text-align: center; 
    }
    
    .matrix-col { 
        background: #222; 
        padding: 2px 4px; 
        border-radius: 2px; 
        border: 1px solid #333; 
    }
    
    .matrix-header { 
        color: #ff9800; 
        font-size: 0.8rem; /* 標題字體 */
        font-weight: bold;
        border-bottom: 1px solid #444; 
        margin-bottom: 2px;
    }
    
    .matrix-cell { 
        display: flex; 
        justify-content: space-between; 
        padding: 1px 0; /* 減少行高 */
        color: #ddd; 
    }
    
    .matrix-label { color: #999; margin-right: 4px; }
    
    .cell-high { color: #00ff00; font-weight: bold; }
    .cell-mid { color: #ffff00; }
    
    .section-title { 
        color: #fff; 
        font-size: 1.3rem; 
        border-left: 5px solid #00ffea; 
        padding-left: 10px; 
        margin: 15px 0 10px 0; 
        font-weight: bold;
    }
    
    /* 狀態標籤 */
    .status-live { color: #ff4b4b; font-weight: bold; animation: pulse 2s infinite; }
    .status-ft { color: #00ffea; }
    .status-ns { color: #888; }
    
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
</style>
""", unsafe_allow_html=True)

# ================= 輔助函數 =================
def clean_pct(val):
    try: return int(float(str(val).replace('%', '')))
    except: return 0

def fmt_pct(val, threshold=50):
    v = clean_pct(val)
    if v == 0: return "-"
    color_cls = 'cell-high' if v >= threshold else ('cell-mid' if v >= threshold - 10 else '')
    return f"<span class='{color_cls}'>{v}%</span>"

def load_data():
    df = pd.DataFrame()
    source = "無"
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = None
        if "gcp_service_account" in st.secrets:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        elif os.path.exists("key.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
            
        if creds:
            client = gspread.authorize(creds)
            sheet = client.open(GOOGLE_SHEET_NAME).sheet1
            df = pd.DataFrame(sheet.get_all_records())
            source = "Cloud"
    except: pass

    if df.empty and os.path.exists(CSV_FILENAME):
        try:
            df = pd.read_csv(CSV_FILENAME)
            source = "CSV"
        except: pass
    return df, source

# ================= 卡片渲染 =================
def render_match_card(row):
    prob_h = clean_pct(row.get('主勝率', 0))
    prob_d = clean_pct(row.get('和率', 0))
    prob_a = clean_pct(row.get('客勝率', 0))
    
    score_txt = f"{row.get('主分')} - {row.get('客分')}" if str(row.get('主分')) not in ['','nan'] else "VS"
    xg_txt = f"xG: {row.get('xG主',0)} - {row.get('xG客',0)}"
    
    status = row.get('狀態')
    status_cls = "status-live" if status == '進行中' else ("status-ft" if status == '完場' else "status-ns")
    
    # 亞盤數據
    ah_pick = row.get('亞盤', '-')
    ah_prob = row.get('亞盤率', 0)
    
    card_html = f"""
    <div class='compact-card'>
        <div class='match-header'>
            <span>{row.get('時間')} | {row.get('聯賽')}</span>
            <span class='{status_cls}'>{status}</span>
        </div>
        <div class='content-row'>
            <div class='teams-area'>
                <div class='team-name'>{row.get('主隊')} <span class='rank-badge'>#{row.get('主排名','?')}</span></div>
                <div class='team-name'>{row.get('客隊')} <span class='rank-badge'>#{row.get('客排名','?')}</span></div>
                <div class='team-sub'>H2H: {row.get('H2H主')}-{row.get('H2H和')}-{row.get('H2H客')} | 源: {row.get('數據源')}</div>
            </div>
            <div class='score-area'>
                <div class='score-main'>{score_txt}</div>
                <div class='score-sub'>{xg_txt}</div>
            </div>
        </div>
        <div class='grid-matrix'>
            <div class='matrix-col'>
                <div class='matrix-header'>勝平負</div>
                <div class='matrix-cell'><span class='matrix-label'>主</span>{fmt_pct(prob_h)}</div>
                <div class='matrix-cell'><span class='matrix-label'>和</span>{fmt_pct(prob_d)}</div>
                <div class='matrix-cell'><span class='matrix-label'>客</span>{fmt_pct(prob_a)}</div>
            </div>
            <div class='matrix-col'>
                <div class='matrix-header'>全場進球</div>
                <div class='matrix-cell'><span class='matrix-label'>>0.5</span>{fmt_pct(row.get('大0.5'), 90)}</div>
                <div class='matrix-cell'><span class='matrix-label'>>1.5</span>{fmt_pct(row.get('大1.5'), 70)}</div>
                <div class='matrix-cell'><span class='matrix-label'>>2.5</span>{fmt_pct(row.get('大2.5'), 55)}</div>
            </div>
            <div class='matrix-col'>
                <div class='matrix-header'>半場/BTTS</div>
                <div class='matrix-cell'><span class='matrix-label'>半>0.5</span>{fmt_pct(row.get('半大0.5'), 65)}</div>
                <div class='matrix-cell'><span class='matrix-label'>半>1.5</span>{fmt_pct(row.get('半大1.5'), 30)}</div>
                <div class='matrix-cell'><span class='matrix-label'>雙進</span>{fmt_pct(row.get('BTTS'), 55)}</div>
            </div>
            <div class='matrix-col'>
                <div class='matrix-header'>亞盤分析</div>
                <div class='matrix-cell' style='justify-content:center; color:#ffd700; font-weight:bold;'>{ah_pick}</div>
                <div class='matrix-cell'><span class='matrix-label'>機率</span>{fmt_pct(ah_prob, 55)}</div>
                <div class='matrix-cell'><span class='matrix-label'>Value</span>{row.get('主Value')}{row.get('客Value')}</div>
            </div>
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

# ================= 主程式 =================
def main():
    # === 側邊欄篩選區 (Top Left) ===
    st.sidebar.title("🛠️ 賽事篩選")
    
    df, source = load_data()
    
    if df.empty:
        st.error("❌ 尚未讀取到數據，請先運行後端腳本。")
        return

    hk_tz = pytz.timezone('Asia/Hong_Kong')
    now = datetime.now(hk_tz)
    
    # 狀態篩選
    all_statuses = ['未開賽', '進行中', '完場', '延期/取消']
    selected_statuses = st.sidebar.multiselect(
        "選擇賽事狀態", 
        all_statuses, 
        default=['未開賽', '進行中'] # 預設不顯示已完場，保持頁面乾淨
    )
    
    # 日期篩選 (自動讀取數據中的日期)
    if '日期' in df.columns:
        available_dates = sorted(df['日期'].unique().tolist())
        selected_dates = st.sidebar.multiselect("選擇日期", available_dates, default=available_dates)
    else:
        selected_dates = []

    # 聯賽篩選
    if '聯賽' in df.columns:
        all_leagues = sorted(df['聯賽'].unique().tolist())
        selected_leagues = st.sidebar.multiselect("選擇聯賽", all_leagues, default=all_leagues)

    # === 主頁面 ===
    st.title("⚽ 足球AI Pro")
    st.caption(f"數據源: {source} | 更新於: {now.strftime('%H:%M')}")

    # 數據過濾邏輯
    filtered_df = df.copy()
    
    if selected_statuses:
        filtered_df = filtered_df[filtered_df['狀態'].isin(selected_statuses)]
    
    if selected_dates and '日期' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['日期'].isin(selected_dates)]
        
    if selected_leagues and '聯賽' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['聯賽'].isin(selected_leagues)]

    # 排序：進行中 -> 未開賽 (按時間) -> 完場
    # 為了排序方便，這裡做一個簡單的權重映射
    status_order = {'進行中': 0, '未開賽': 1, '完場': 2, '延期/取消': 3}
    filtered_df['status_rank'] = filtered_df['狀態'].map(status_order)
    
    # 先按狀態排，再按時間排
    filtered_df = filtered_df.sort_values(by=['status_rank', '時間'])

    # 顯示結果
    if not filtered_df.empty:
        count = len(filtered_df)
        st.markdown(f"<div class='section-title'>📋 賽事列表 ({count} 場)</div>", unsafe_allow_html=True)
        for _, row in filtered_df.iterrows():
            render_match_card(row)
    else:
        st.info("🔍 根據目前的篩選條件，沒有找到賽事。請嘗試調整左側篩選器。")

    # Raw Data View
    with st.expander("查看原始表格數據"):
        st.dataframe(filtered_df)

if __name__ == "__main__":
    main()
