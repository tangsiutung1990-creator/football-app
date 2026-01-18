import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import math

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI Pro (Real Data)", page_icon="⚽", layout="wide")

# ================= CSS 優化 (專業黑金風格) =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    
    /* 卡片容器 */
    .match-card { 
        background-color: #1a1c24; 
        border: 1px solid #333; 
        border-radius: 12px; 
        padding: 15px; 
        margin-bottom: 15px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* 頂部資訊 */
    .match-header { 
        display: flex; justify-content: space-between; 
        color: #888; font-size: 0.8rem; margin-bottom: 10px; border-bottom: 1px solid #2d2d2d; padding-bottom: 5px;
    }
    
    /* 比分與球隊 */
    .score-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 15px; }
    .team-box { width: 40%; text-align: center; }
    .team-name { font-size: 1.1rem; font-weight: bold; color: #fff; margin-bottom: 4px; }
    .team-meta { font-size: 0.75rem; color: #aaa; }
    .score-box { width: 20%; font-size: 2rem; font-weight: bold; color: #00e5ff; text-align: center; letter-spacing: 2px; }
    .status-live { color: #ff4b4b; font-size: 0.8rem; font-weight: bold; animation: pulse 1.5s infinite; }
    
    /* 數據網格 (Pro 分析核心) */
    .analysis-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
    .data-col { background: #222; border-radius: 8px; padding: 8px; border: 1px solid #333; }
    .col-title { font-size: 0.75rem; color: #ffd700; font-weight: bold; text-transform: uppercase; margin-bottom: 6px; border-bottom: 1px dashed #444; }
    
    /* 數據行 */
    .stat-row { display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 4px; align-items: center; }
    .stat-label { color: #ccc; }
    .stat-val { color: #fff; font-weight: bold; }
    .stat-val.high { color: #00ff00; }
    .odds-tag { background: #333; color: #fff; padding: 1px 4px; border-radius: 3px; font-size: 0.75rem; border: 1px solid #555; }
    
    /* 底部標籤 */
    .footer-tags { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 10px; padding-top: 8px; border-top: 1px solid #2d2d2d; }
    .tag { font-size: 0.7rem; padding: 2px 8px; border-radius: 4px; background: #333; color: #ddd; }
    .tag-pick { background: linear-gradient(45deg, #00b09b, #96c93d); color: #000; font-weight: bold; }
    .tag-ev { background: linear-gradient(45deg, #FFD700, #FFA500); color: #000; font-weight: bold; }

    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
</style>
""", unsafe_allow_html=True)

# ================= 輔助函式 =================
def clean_pct(val):
    """清除 % 符號並轉為浮點數，處理空值"""
    if pd.isna(val) or val == '': return 0.0
    try:
        s = str(val).replace('%', '').strip()
        return float(s)
    except: return 0.0

def get_form_html(form_str):
    if pd.isna(form_str) or str(form_str) == 'N/A' or str(form_str) == '?????': return ""
    html = ""
    for char in str(form_str).strip()[-5:]:
        color = "#28a745" if char.upper()=='W' else "#ffc107" if char.upper()=='D' else "#dc3545"
        html += f"<span style='color:{color}; font-weight:bold; margin:0 1px;'>{char}</span>"
    return html

# ================= 連接 Google Sheet =================
@st.cache_data(ttl=60) 
def load_data():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        # 兼容 Streamlit Cloud 與 本地環境
        if os.path.exists("key.json"): creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        else: creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e: return None

# ================= 主程式 =================
def main():
    st.title("⚽ 足球AI Pro (Real Data Edition)")
    
    col1, col2 = st.columns([8, 1])
    with col2:
        if st.button("🔄"): 
            st.cache_data.clear()
            st.rerun()

    df = load_data()
    if df is None or df.empty:
        st.warning("⚠️ 暫無數據，請確認 run_me.py 是否已成功上傳真實數據。")
        return

    # === 數據前處理 (適配 V17 格式) ===
    # 確保數值欄位可用，防止 KeyError
    numeric_cols = ['主勝賠率', '客勝賠率']
    for c in numeric_cols:
        if c not in df.columns: df[c] = 0 # 若欄位缺失則補 0
        else: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

    # === 側邊欄篩選 ===
    st.sidebar.header("🔍 賽事篩選")
    
    # 日期篩選
    if '時間' in df.columns:
        df['日期'] = df['時間'].apply(lambda x: str(x).split(' ')[0])
        all_dates = sorted(list(set(df['日期'])))
        sel_date = st.sidebar.selectbox("📅 日期", ["全部"] + all_dates)
        if sel_date != "全部": df = df[df['日期'] == sel_date]

    # 聯賽篩選
    if '聯賽' in df.columns:
        all_leagues = sorted(list(set(df['聯賽'].astype(str))))
        sel_lg = st.sidebar.selectbox("🏆 聯賽", ["全部"] + all_leagues)
        if sel_lg != "全部": df = df[df['聯賽'] == sel_lg]

    # 狀態排序
    if '狀態' in df.columns:
        df['sort_idx'] = df['狀態'].apply(lambda x: 0 if x in ['進行中','中場休息'] else 1 if x=='未開賽' else 2)
        df = df.sort_values(by=['sort_idx', '時間'])

    # === 顯示卡片 ===
    for index, row in df.iterrows():
        # 讀取 AI 概率 (適配 V17 新欄位名稱)
        # 注意: 這裡讀取的是 '大球率' 而不是 '大球率2.5'
        prob_h = clean_pct(row.get('主勝率', 0))
        prob_d = clean_pct(row.get('和局率', 0))
        prob_a = clean_pct(row.get('客勝率', 0))
        prob_o25 = clean_pct(row.get('大球率', 0)) 
        prob_btts = clean_pct(row.get('BTTS率', 0))
        
        # 讀取真實賠率
        odd_h = row.get('主勝賠率', 0)
        odd_a = row.get('客勝賠率', 0)
        
        # 樣式邏輯
        pick = row.get('首選推介', '')
        tags = row.get('智能標籤', '')
        status = row.get('狀態', '未開賽')
        status_html = f"<span class='status-live'>● {status}</span>" if status in ['進行中','中場休息'] else status
        
        # HTML 構建
        st.markdown(f"""
        <div class='match-card'>
            <div class='match-header'>
                <span>{row.get('時間','')} &nbsp;|&nbsp; {row.get('聯賽','')}</span>
                <span>{status_html}</span>
            </div>

            <div class='score-row'>
                <div class='team-box'>
                    <div class='team-name'>{row.get('主隊','')} <span style='font-size:0.8rem; color:#888;'>#{row.get('主排名','-')}</span></div>
                    <div class='team-meta'>{get_form_html(row.get('主近況'))}</div>
                </div>
                <div class='score-box'>
                    {row.get('主分','')} - {row.get('客分','')}
                </div>
                <div class='team-box'>
                    <div class='team-name'>{row.get('客隊','')} <span style='font-size:0.8rem; color:#888;'>#{row.get('客排名','-')}</span></div>
                    <div class='team-meta'>{get_form_html(row.get('客近況'))}</div>
                </div>
            </div>

            <div class='analysis-grid'>
                <div class='data-col'>
                    <div class='col-title'>勝平負 (1x2) 模型</div>
                    <div class='stat-row'>
                        <span class='stat-label'>主勝</span>
                        <div>
                            <span class='stat-val {"high" if prob_h > 50 else ""}'>{prob_h}%</span>
                            <span class='odds-tag' title='真實賠率'>{odd_h if odd_h > 0 else '-'}</span>
                        </div>
                    </div>
                    <div class='stat-row'>
                        <span class='stat-label'>和局</span>
                        <span class='stat-val'>{prob_d}%</span>
                    </div>
                    <div class='stat-row'>
                        <span class='stat-label'>客勝</span>
                        <div>
                            <span class='stat-val {"high" if prob_a > 50 else ""}'>{prob_a}%</span>
                            <span class='odds-tag' title='真實賠率'>{odd_a if odd_a > 0 else '-'}</span>
                        </div>
                    </div>
                </div>

                <div class='data-col'>
                    <div class='col-title'>入球概率模型</div>
                    <div class='stat-row'>
                        <span class='stat-label'>大球 2.5 (Over)</span>
                        <span class='stat-val {"high" if prob_o25 > 55 else ""}'>{prob_o25}%</span>
                    </div>
                    <div class='stat-row'>
                        <span class='stat-label'>細球 2.5 (Under)</span>
                        <span class='stat-val'>{round(100-prob_o25, 1)}%</span>
                    </div>
                    <div class='stat-row'>
                        <span class='stat-label'>雙方入球 (BTTS)</span>
                        <span class='stat-val {"high" if prob_btts > 55 else ""}'>{prob_btts}%</span>
                    </div>
                </div>
            </div>

            <div class='footer-tags'>
                <span class='tag tag-pick'>🎯 推介: {pick}</span>
                {''.join([f"<span class='tag tag-ev'>{t}</span>" for t in tags.split(' ') if 'EV' in t])}
                {'<span class="tag">📊 已開盤</span>' if odd_h > 0 else '<span class="tag">⏳ 未開盤</span>'}
            </div>
        </div>
        """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
