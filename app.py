import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import math
import os
from datetime import datetime

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI Compact Pro (V15.5)", page_icon="⚽", layout="wide")

# ================= CSS =================
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    
    /* V15.5 Compact Style */
    .compact-card { background-color: #1a1c24; border: 1px solid #333; border-radius: 8px; padding: 10px; margin-bottom: 8px; font-size: 0.8rem; }
    
    .match-header { display: flex; justify-content: space-between; color: #aaa; font-size: 0.75rem; margin-bottom: 5px; border-bottom: 1px solid #333; padding-bottom: 2px; }
    
    .team-row { display: grid; grid-template-columns: 3fr 1fr 3fr; align-items: center; margin-bottom: 8px; }
    .team-name { font-weight: bold; font-size: 1rem; color: #fff; }
    .team-score { font-size: 1.2rem; font-weight: bold; color: #00ffea; text-align: center; }
    
    .grid-stats { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 4px; font-size: 0.75rem; margin-top: 5px; }
    .stat-cell { background: #25262b; padding: 4px; border-radius: 4px; text-align: center; border: 1px solid #444; }
    .stat-label { color: #888; font-size: 0.65rem; margin-bottom: 1px; }
    .stat-val { color: #fff; font-weight: bold; }
    
    .h2h-line { font-size: 0.7rem; color: #ffd700; text-align: center; margin-top: 4px; letter-spacing: 2px; }
    
    .rec-box { background: linear-gradient(90deg, #2c3e50, #4ca1af); padding: 5px; border-radius: 4px; text-align: center; margin-top: 5px; font-weight: bold; color: #fff; border: 1px solid #555; }
    
    .risk-tag { font-size: 0.65rem; padding: 1px 4px; border-radius: 3px; background: #444; color: #ddd; margin-right: 3px; }
    
    /* Pro Matrix Colors */
    .prob-high { color: #00ff00; }
    .prob-med { color: #ffeb3b; }
    .prob-low { color: #ff4b4b; }
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
    st.title("⚽ 足球AI Compact Pro (V15.5)")
    
    df = load_data()
    if df is not None and not df.empty:
        total = len(df)
        live = len(df[df['狀態'].astype(str).str.contains("進行中")])
        st.markdown(f"<div style='margin-bottom:10px; font-size:0.8rem; color:#888;'>賽事總數: {total} | 進行中: {live}</div>", unsafe_allow_html=True)
    
    if st.button("🔄 刷新數據"): 
        st.cache_data.clear()
        st.rerun()

    if df is None or df.empty: return

    # 數據整理
    num_cols = ['xG主','xG客','主勝率','和局率','客勝率','AH-0.5','AH-1.0','AH-2.0','C75','C85','C95',
                '大球率2.5','最低賠率主','最低賠率客','合理大賠2.5']
    for col in num_cols: 
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    st.sidebar.header("🔍 篩選")
    leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
    sel_lg = st.sidebar.selectbox("聯賽:", leagues)
    
    df['日期'] = df['時間'].apply(lambda x: str(x).split(' ')[0])
    dates = ["全部"] + sorted(list(set(df['日期'])))
    sel_date = st.sidebar.selectbox("日期:", dates)

    if sel_lg != "全部": df = df[df['聯賽'] == sel_lg]
    if sel_date != "全部": df = df[df['日期'] == sel_date]

    # === 渲染 Compact Card ===
    for index, row in df.iterrows():
        time_part = str(row['時間']).split(' ')[1]
        
        # 數據提取
        xg_h = row.get('xG主', 0); xg_a = row.get('xG客', 0)
        p_h = row.get('主勝率', 0); p_d = row.get('和局率', 0); p_a = row.get('客勝率', 0)
        p_o25 = row.get('大球率2.5', 0)
        
        ah05 = row.get('AH-0.5', 0); ah1 = row.get('AH-1.0', 0); ah2 = row.get('AH-2.0', 0)
        c75 = row.get('C75', 0); c85 = row.get('C85', 0); c95 = row.get('C95', 0)
        
        min_h = row.get('最低賠率主', 0); min_a = row.get('最低賠率客', 0)
        
        top_pick = row.get('首選推介', '')
        risk = row.get('風險評級', '')
        
        # HTML 結構
        html = f"""
        <div class='compact-card'>
            <div class='match-header'>
                <span>{time_part} | {row['聯賽']}</span>
                <span>{row['狀態']}</span>
            </div>
            
            <div class='team-row'>
                <div style='text-align:right;'>
                    <div class='team-name'>{row['主隊']}</div>
                    <div style='font-size:0.7rem; color:#aaa;'>xG:{xg_h} | {get_form_html(row.get('主近況'))}</div>
                </div>
                <div class='team-score'>{row['主分']} - {row['客分']}</div>
                <div>
                    <div class='team-name'>{row['客隊']}</div>
                    <div style='font-size:0.7rem; color:#aaa;'>xG:{xg_a} | {get_form_html(row.get('客近況'))}</div>
                </div>
            </div>
            
            <div class='h2h-line'>{row.get('H2H', '')}</div>
            
            <div class='grid-stats'>
                <div class='stat-cell'>
                    <div class='stat-label'>主勝 ({p_h}%)</div>
                    <div class='stat-val' style='color:{'#00ff00' if p_h>50 else '#fff'}'>需 > {fmt_odd(min_h)}</div>
                </div>
                <div class='stat-cell'>
                    <div class='stat-label'>和局 ({p_d}%)</div>
                    <div class='stat-val'>---</div>
                </div>
                <div class='stat-cell'>
                    <div class='stat-label'>客勝 ({p_a}%)</div>
                    <div class='stat-val' style='color:{'#00ff00' if p_a>50 else '#fff'}'>需 > {fmt_odd(min_a)}</div>
                </div>
                
                <div class='stat-cell'>
                    <div class='stat-label'>讓 -0.5</div>
                    <div class='stat-val'>{ah05}%</div>
                </div>
                <div class='stat-cell'>
                    <div class='stat-label'>讓 -1.0</div>
                    <div class='stat-val'>{ah1}%</div>
                </div>
                <div class='stat-cell'>
                    <div class='stat-label'>讓 -2.0</div>
                    <div class='stat-val'>{ah2}%</div>
                </div>
                
                <div class='stat-cell'>
                    <div class='stat-label'>角 > 7.5</div>
                    <div class='stat-val'>{c75}%</div>
                </div>
                <div class='stat-cell'>
                    <div class='stat-label'>角 > 8.5</div>
                    <div class='stat-val'>{c85}%</div>
                </div>
                <div class='stat-cell'>
                    <div class='stat-label'>角 > 9.5</div>
                    <div class='stat-val'>{c95}%</div>
                </div>
            </div>
            
            <div class='rec-box'>
                🎯 {top_pick} <span style='font-size:0.7rem; font-weight:normal; margin-left:5px;'>({risk})</span>
            </div>
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
