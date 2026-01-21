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

# ================= CSS 優化 =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    
    .compact-card { background-color: #1a1c24; border: 1px solid #333; border-radius: 8px; padding: 10px; margin-bottom: 10px; font-family: 'Arial', sans-serif; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
    
    .match-header { display: flex; justify-content: space-between; color: #888; font-size: 0.8rem; margin-bottom: 8px; border-bottom: 1px solid #333; padding-bottom: 4px; }
    
    .content-row { display: grid; grid-template-columns: 6fr 4fr; align-items: center; margin-bottom: 10px; }
    .teams-area { text-align: left; }
    
    .team-name { font-weight: bold; font-size: 1.1rem; color: #fff; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; } 
    .team-sub { font-size: 0.75rem; color: #aaa; display: flex; gap: 8px; align-items: center; }
    
    .rank-badge { background: #555; color: #fff; font-size: 0.7rem; padding: 1px 4px; border-radius: 3px; }
    
    .score-area { text-align: right; }
    .score-main { font-size: 1.8rem; font-weight: bold; color: #00ffea; }
    
    .grid-matrix { display: grid; grid-template-columns: repeat(4, 1fr); gap: 2px; font-size: 0.7rem; margin-top: 8px; text-align: center; }
    .matrix-col { background: #222; padding: 2px; border-radius: 4px; border: 1px solid #333; }
    .matrix-header { color: #ff9800; font-size: 0.7rem; border-bottom: 1px solid #444; }
    .matrix-cell { display: flex; justify-content: space-between; padding: 0 4px; color: #ccc; }
    
    .cell-high { color: #00ff00; font-weight: bold; }
    .section-title { color: #fff; font-size: 1.2rem; border-left: 4px solid #00ffea; padding-left: 10px; margin: 20px 0 10px 0; }
</style>
""", unsafe_allow_html=True)

# ================= 輔助函數 =================
def clean_pct(val):
    try: return int(float(str(val).replace('%', '')))
    except: return 0

def fmt_pct(val, threshold=50):
    v = clean_pct(val)
    if v == 0: return "-"
    return f"<span class='{'cell-high' if v > threshold else ''}'>{v}%</span>"

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
            source = "Google Cloud"
    except: pass

    if df.empty and os.path.exists(CSV_FILENAME):
        try:
            df = pd.read_csv(CSV_FILENAME)
            source = "Local CSV"
        except: pass
    return df, source

# ================= 卡片渲染 =================
def render_match_card(row):
    prob_h = clean_pct(row.get('主勝率', 0))
    prob_d = clean_pct(row.get('和率', 0))
    prob_a = clean_pct(row.get('客勝率', 0))
    
    score_txt = f"{row.get('主分')} - {row.get('客分')}" if str(row.get('主分')) not in ['','nan'] else "VS"
    xg_txt = f"xG: {row.get('xG主',0)} - {row.get('xG客',0)}"
    
    card_html = f"""
    <div class='compact-card'>
        <div class='match-header'>
            <span>{row.get('時間')} | {row.get('聯賽')}</span>
            <span>{row.get('狀態')}</span>
        </div>
        <div class='content-row'>
            <div class='teams-area'>
                <div class='team-name'>{row.get('主隊')} <span class='rank-badge'>#{row.get('主排名','?')}</span></div>
                <div class='team-name'>{row.get('客隊')} <span class='rank-badge'>#{row.get('客排名','?')}</span></div>
                <div class='team-sub'>亞盤建議: <span style='color:#ffd700'>{row.get('亞盤','-')}</span></div>
            </div>
            <div class='score-area'>
                <div class='score-main'>{score_txt}</div>
                <div style='font-size:0.7rem; color:#888'>{xg_txt}</div>
            </div>
        </div>
        <div class='grid-matrix'>
            <div class='matrix-col'>
                <div class='matrix-header'>勝平負 %</div>
                <div class='matrix-cell'><span>主</span>{fmt_pct(prob_h)}</div>
                <div class='matrix-cell'><span>和</span>{fmt_pct(prob_d)}</div>
                <div class='matrix-cell'><span>客</span>{fmt_pct(prob_a)}</div>
            </div>
            <div class='matrix-col'>
                <div class='matrix-header'>全場進球 %</div>
                <div class='matrix-cell'><span>>1.5</span>{fmt_pct(row.get('大1.5'), 70)}</div>
                <div class='matrix-cell'><span>>2.5</span>{fmt_pct(row.get('大2.5'), 55)}</div>
                <div class='matrix-cell'><span>>3.5</span>{fmt_pct(row.get('大3.5'), 40)}</div>
            </div>
            <div class='matrix-col'>
                <div class='matrix-header'>半場/保守 %</div>
                <div class='matrix-cell'><span>半>0.5</span>{fmt_pct(row.get('半大0.5'), 65)}</div>
                <div class='matrix-cell'><span>半>1.5</span>{fmt_pct(row.get('半大1.5'), 35)}</div>
                <div class='matrix-cell'><span>全>0.5</span>{fmt_pct(row.get('大0.5'), 90)}</div>
            </div>
            <div class='matrix-col'>
                <div class='matrix-header'>H2H/BTTS</div>
                <div class='matrix-cell'><span>交鋒</span>{row.get('H2H主')}-{row.get('H2H和')}-{row.get('H2H客')}</div>
                <div class='matrix-cell'><span>BTTS</span>{fmt_pct(row.get('BTTS'), 55)}</div>
                <div class='matrix-cell'><span>Value</span>{row.get('主Value')}{row.get('客Value')}</div>
            </div>
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

# ================= 主程式 =================
def main():
    st.title("⚽ 足球AI Pro (精選版)")
    df, source = load_data()

    if df.empty:
        st.error("❌ 無數據。")
        return

    hk_tz = pytz.timezone('Asia/Hong_Kong')
    now = datetime.now(hk_tz)
    today_str = now.strftime('%Y-%m-%d')
    yesterday_str = (now - timedelta(days=1)).strftime('%Y-%m-%d')

    st.info(f"📅 資料來源: {source} | 更新時間: {now.strftime('%H:%M')}")

    # 確保有日期列，如果沒有則嘗試從時間列提取
    if '日期' not in df.columns and '時間' in df.columns:
        df['日期'] = df['時間'].apply(lambda x: x.split(' ')[0])

    # === 邏輯：篩選昨日完場 (5場) ===
    # 條件：日期是昨天 且 狀態是完場
    mask_yesterday = (df['日期'] == yesterday_str) & (df['狀態'] == '完場')
    df_yesterday = df[mask_yesterday].copy()
    # 排序：按時間倒序 (最近完場的在上面) 或 按關注度/聯賽排序，這裡簡單按時間
    df_yesterday = df_yesterday.sort_values(by='時間', ascending=False).head(5)

    # === 邏輯：篩選今日未開賽 (5場) ===
    # 條件：日期是今天 且 狀態是未開賽
    mask_today = (df['日期'] == today_str) & (df['狀態'] == '未開賽')
    df_today = df[mask_today].copy()
    # 排序：按時間正序 (即將開賽的在上面)
    df_today = df_today.sort_values(by='時間', ascending=True).head(5)

    # === 顯示區域 ===
    
    st.markdown(f"<div class='section-title'>🔥 今日精選 (即將開賽 Top 5) - {today_str}</div>", unsafe_allow_html=True)
    if not df_today.empty:
        for _, row in df_today.iterrows():
            render_match_card(row)
    else:
        st.write("今日暫無符合條件的未開賽賽事。")

    st.markdown(f"<div class='section-title'>⏮️ 昨日回顧 (完場 Top 5) - {yesterday_str}</div>", unsafe_allow_html=True)
    if not df_yesterday.empty:
        for _, row in df_yesterday.iterrows():
            render_match_card(row)
    else:
        st.write("昨日暫無完場賽事記錄。")

    # 調試用：顯示所有數據 (可選)
    with st.expander("查看所有抓取數據"):
        st.dataframe(df)

if __name__ == "__main__":
    main()
