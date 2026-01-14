import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import math
import os
from datetime import datetime

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI Stability Ultimate (V15.7)", page_icon="⚽", layout="wide")

# ================= CSS =================
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    
    /* V15.7 Style */
    .compact-card { background-color: #1a1c24; border: 1px solid #333; border-radius: 8px; padding: 10px; margin-bottom: 8px; font-size: 0.8rem; }
    .match-header { display: flex; justify-content: space-between; color: #aaa; font-size: 0.75rem; margin-bottom: 5px; border-bottom: 1px solid #333; padding-bottom: 2px; }
    .team-row { display: grid; grid-template-columns: 3fr 1fr 3fr; align-items: center; margin-bottom: 8px; }
    .team-name { font-weight: bold; font-size: 1rem; color: #fff; }
    .team-score { font-size: 1.2rem; font-weight: bold; color: #00ffea; text-align: center; }
    .info-sub { font-size: 0.7rem; color: #888; }
    
    /* 5-Column Matrix */
    .grid-matrix { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr 1fr; gap: 4px; font-size: 0.7rem; margin-top: 5px; text-align: center; }
    .matrix-col { display: flex; flex-direction: column; gap: 2px; border-right: 1px solid #333; padding-right: 2px; }
    .matrix-col:last-child { border-right: none; }
    .matrix-header { color: #ff9800; font-weight: bold; margin-bottom: 2px; border-bottom: 1px dashed #444; }
    .matrix-cell { display: flex; justify-content: space-between; padding: 1px 4px; background: #25262b; border-radius: 2px; margin-bottom: 1px; }
    .cell-label { color: #aaa; }
    .cell-val { color: #fff; font-weight: bold; }
    
    .rec-box { background: linear-gradient(90deg, #1cb5e0, #000046); padding: 5px; border-radius: 4px; text-align: center; margin-top: 5px; font-weight: bold; color: #fff; border: 1px solid #555; display: flex; justify-content: space-between; align-items: center; }
    .ah-sugg { color: #00ff00; font-size: 0.75rem; margin-top: 4px; text-align: center; border: 1px dashed #444; border-radius: 4px; }
    </style>
    """, unsafe_allow_html=True)

# ================= 輔助函式 =================
def get_form_html(form_str):
    if pd.isna(form_str) or str(form_str) == 'N/A': return "-"
    html = ""
    for char in str(form_str).strip()[-5:]:
        c = "#28a745" if char.upper()=='W' else "#ffc107" if char.upper()=='D' else "#dc3545"
        html += f"<span style='color:{c}; font-weight:bold;'>{char}</span>"
    return html

def fmt_odd(val): return f"{val:.2f}" if val < 50 else "-"

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
    except Exception as e: return None

# ================= 主程式 =================
def main():
    st.title("⚽ 足球AI Stability Ultimate (V15.7)")
    
    try:
        df = load_data()
        if df is not None and not df.empty:
            if st.button("🔄 刷新數據"): 
                st.cache_data.clear()
                st.rerun()
        else:
            st.warning("⚠️ 無法讀取數據，請檢查 run_me.py 是否執行成功。")
            return

        # 數據整理 (Error Handling: 缺少欄位自動補 0)
        req_cols = ['xG主','xG客','主勝率','和局率','客勝率','HT主','HT和','HT客','AH-0.5','AH-1.0','AH-2.0',
                    'C75','C85','C95','大球率1.5','大球率2.5','大球率3.5','最低賠率主','最低賠率客']
        
        # 檢查是否為舊版數據
        if 'HT主' not in df.columns:
            st.error("🚨 檢測到舊版數據結構！請務必重新執行一次 `run_me.py` (V15.7) 以更新資料庫。")
            return

        for col in req_cols: 
            if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        st.sidebar.header("🔍 篩選")
        leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
        sel_lg = st.sidebar.selectbox("聯賽:", leagues)
        
        df['日期'] = df['時間'].apply(lambda x: str(x).split(' ')[0])
        dates = ["全部"] + sorted(list(set(df['日期'])))
        sel_date = st.sidebar.selectbox("日期:", dates)

        if sel_lg != "全部": df = df[df['聯賽'] == sel_lg]
        if sel_date != "全部": df = df[df['日期'] == sel_date]

        # === 渲染 Compact Matrix ===
        for index, row in df.iterrows():
            time_part = str(row['時間']).split(' ')[1]
            
            html = f"""
            <div class='compact-card'>
                <div class='match-header'>
                    <span>{time_part} | {row['聯賽']}</span>
                    <span>{row['狀態']}</span>
                </div>
                
                <div class='team-row'>
                    <div style='text-align:right;'>
                        <div class='team-name'>{row['主隊']}</div>
                        <div class='info-sub'>xG:{row.get('xG主')} | {get_form_html(row.get('主近況'))}</div>
                    </div>
                    <div class='team-score'>{row['主分']} - {row['客分']}</div>
                    <div>
                        <div class='team-name'>{row['客隊']}</div>
                        <div class='info-sub'>xG:{row.get('xG客')} | {get_form_html(row.get('客近況'))}</div>
                    </div>
                </div>
                
                <div style='text-align:center; font-size:0.7rem; color:#aaa; margin-bottom:5px;'>對賽: {row.get('H2H', '')}</div>
                
                <div class='grid-matrix'>
                    <div class='matrix-col'>
                        <div class='matrix-header'>全場</div>
                        <div class='matrix-cell'><span class='cell-label'>主</span><span class='cell-val'>{row.get('主勝率')}%</span></div>
                        <div class='matrix-cell'><span class='cell-label'>和</span><span class='cell-val'>{row.get('和局率')}%</span></div>
                        <div class='matrix-cell'><span class='cell-label'>客</span><span class='cell-val'>{row.get('客勝率')}%</span></div>
                    </div>
                    <div class='matrix-col'>
                        <div class='matrix-header'>半場</div>
                        <div class='matrix-cell'><span class='cell-label'>主</span><span class='cell-val'>{row.get('HT主')}%</span></div>
                        <div class='matrix-cell'><span class='cell-label'>和</span><span class='cell-val'>{row.get('HT和')}%</span></div>
                        <div class='matrix-cell'><span class='cell-label'>客</span><span class='cell-val'>{row.get('HT客')}%</span></div>
                    </div>
                    <div class='matrix-col'>
                        <div class='matrix-header'>亞盤(主)</div>
                        <div class='matrix-cell'><span class='cell-label'>-0.5</span><span class='cell-val'>{row.get('AH-0.5')}%</span></div>
                        <div class='matrix-cell'><span class='cell-label'>-1.0</span><span class='cell-val'>{row.get('AH-1.0')}%</span></div>
                        <div class='matrix-cell'><span class='cell-label'>-2.0</span><span class='cell-val'>{row.get('AH-2.0')}%</span></div>
                    </div>
                    <div class='matrix-col'>
                        <div class='matrix-header'>大小球</div>
                        <div class='matrix-cell'><span class='cell-label'>1.5</span><span class='cell-val'>{row.get('大球率1.5')}%</span></div>
                        <div class='matrix-cell'><span class='cell-label'>2.5</span><span class='cell-val'>{row.get('大球率2.5')}%</span></div>
                        <div class='matrix-cell'><span class='cell-label'>3.5</span><span class='cell-val'>{row.get('大球率3.5')}%</span></div>
                    </div>
                    <div class='matrix-col'>
                        <div class='matrix-header'>角球</div>
                        <div class='matrix-cell'><span class='cell-label'>7.5</span><span class='cell-val'>{row.get('C75')}%</span></div>
                        <div class='matrix-cell'><span class='cell-label'>8.5</span><span class='cell-val'>{row.get('C85')}%</span></div>
                        <div class='matrix-cell'><span class='cell-label'>9.5</span><span class='cell-val'>{row.get('C95')}%</span></div>
                    </div>
                </div>
                
                <div class='ah-sugg'>建議: {row.get('亞盤建議')} | 預計角球: {row.get('角球預測')}</div>
                
                <div class='rec-box'>
                    <span style='font-size:0.9rem;'>🎯 {row.get('首選推介')}</span>
                    <span style='font-size:0.7rem; color:#eee;'>{row.get('風險評級')}</span>
                </div>
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)
            
    except Exception as e:
        st.error(f"應用程式發生錯誤: {e}")
        st.info("建議檢查: 1. `run_me.py` 是否執行成功  2. Google Sheet 連線是否正常")

if __name__ == "__main__":
    main()
