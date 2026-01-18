import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import math

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI Pro (V18.0)", page_icon="⚽", layout="wide")

# ================= CSS 優化 =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .compact-card { background-color: #1a1c24; border: 1px solid #333; border-radius: 12px; padding: 12px; margin-bottom: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    .match-header { display: flex; justify-content: space-between; color: #bbb; font-size: 0.85rem; margin-bottom: 8px; border-bottom: 1px solid #333; padding-bottom: 4px; }
    .team-row { display: grid; grid-template-columns: 3fr 1fr 3fr; align-items: center; margin-bottom: 10px; }
    .team-name { font-weight: bold; font-size: 1.2rem; color: #fff; } 
    .team-meta { font-size: 0.8rem; color: #ccc; }
    .score-box { font-size: 1.8rem; font-weight: bold; color: #00ffea; text-align: center; }
    .grid-matrix { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr 1fr; gap: 4px; font-size: 0.8rem; margin-top: 8px; text-align: center; }
    .matrix-col { background: #222; padding: 4px; border-radius: 6px; border: 1px solid #333; }
    .matrix-header { color: #ff9800; font-weight: bold; font-size: 0.7rem; margin-bottom: 3px; border-bottom: 1px dashed #444; }
    .matrix-cell { display: flex; justify-content: space-between; padding: 2px 4px; }
    .cell-val { color: #fff; font-weight: bold; }
    .cell-val-high { color: #00ff00; font-weight: bold; }
    .footer-box { display: flex; justify-content: space-between; margin-top: 8px; background: #16181d; padding: 6px; border-radius: 6px; }
    .tag { font-size: 0.7rem; padding: 2px 6px; border-radius: 4px; background: #333; color: #ddd; margin-left: 4px; }
    .tag-pick { background: #00b09b; color: #000; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ================= 數據處理函式 =================
def clean_pct(val):
    """智能清洗百分比數據"""
    if pd.isna(val) or val == '': return 0.0
    try:
        s = str(val).replace('%', '').strip()
        f = float(s)
        # 如果數據是小數 (例如 0.75)，轉換為 75
        if f < 1.0 and f > 0: return f * 100
        return f
    except: return 0.0

def get_form_html(form_str):
    if pd.isna(form_str) or str(form_str) in ['N/A', '?????']: return "-"
    html = ""
    for char in str(form_str).strip()[-5:]:
        color = "#28a745" if char.upper()=='W' else "#ffc107" if char.upper()=='D' else "#dc3545"
        html += f"<span style='color:{color}; font-weight:bold; margin-left:2px;'>{char}</span>"
    return html

# ================= 主程式 =================
def main():
    st.title("⚽ 足球AI Pro (V18.0)")
    
    # 連接 Google Sheet
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if os.path.exists("key.json"): creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        else: creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
    except:
        st.error("無法連接數據庫，請檢查 key.json")
        return

    if df.empty:
        st.warning("⚠️ 數據庫為空，請先運行後端程式 (run_me.py)")
        return

    # === 側邊欄 ===
    st.sidebar.header("🔍 篩選")
    if '聯賽' in df.columns:
        leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
        sel_lg = st.sidebar.selectbox("聯賽:", leagues)
        if sel_lg != "全部": df = df[df['聯賽'] == sel_lg]

    # === 渲染列表 ===
    for index, row in df.iterrows():
        # 容錯讀取數據 (優先讀新欄位，兼容舊欄位)
        prob_h = clean_pct(row.get('主勝率', 0))
        prob_a = clean_pct(row.get('客勝率', 0))
        # 兼容 '大球率' 和 '大球率2.5'
        prob_o25 = clean_pct(row.get('大球率', row.get('大球率2.5', 0))) 
        
        cls_h = "cell-val-high" if prob_h > 50 else "cell-val"
        cls_a = "cell-val-high" if prob_a > 50 else "cell-val"
        cls_o25 = "cell-val-high" if prob_o25 > 55 else "cell-val"

        html = f"""
        <div class='compact-card'>
            <div class='match-header'>
                <span>{row.get('時間','')} | {row.get('聯賽','')}</span>
                <span>{row.get('狀態','')}</span>
            </div>
            
            <div class='team-row'>
                <div style='text-align:right;'>
                    <div class='team-name'>{row.get('主隊','')} <span style='font-size:0.8rem; color:#888;'>#{row.get('主排名','-')}</span></div>
                    <div class='team-meta'>{get_form_html(row.get('主近況'))}</div>
                </div>
                <div class='score-box'>{row.get('主分','')} - {row.get('客分','')}</div>
                <div>
                    <div class='team-name'><span style='font-size:0.8rem; color:#888;'>#{row.get('客排名','-')}</span> {row.get('客隊','')}</div>
                    <div class='team-meta'>{get_form_html(row.get('客近況'))}</div>
                </div>
            </div>
            
            <div class='grid-matrix'>
                <div class='matrix-col'>
                    <div class='matrix-header'>勝率模型</div>
                    <div class='matrix-cell'><span>主</span><span class='{cls_h}'>{prob_h:.0f}%</span></div>
                    <div class='matrix-cell'><span>客</span><span class='{cls_a}'>{prob_a:.0f}%</span></div>
                </div>
                <div class='matrix-col'>
                    <div class='matrix-header'>入球模型</div>
                    <div class='matrix-cell'><span>大2.5</span><span class='{cls_o25}'>{prob_o25:.0f}%</span></div>
                    <div class='matrix-cell'><span>BTTS</span><span class='cell-val'>{clean_pct(row.get('BTTS率', row.get('BTTS',0))):.0f}%</span></div>
                </div>
                <div class='matrix-col'>
                    <div class='matrix-header'>投資價值 (Kelly)</div>
                    <div class='matrix-cell'><span>主</span><span class='cell-val'>{clean_pct(row.get('凱利主',0)):.0f}%</span></div>
                    <div class='matrix-cell'><span>客</span><span class='cell-val'>{clean_pct(row.get('凱利客',0)):.0f}%</span></div>
                </div>
                <div class='matrix-col'>
                    <div class='matrix-header'>亞盤建議</div>
                    <div style='color:#00e5ff; font-weight:bold; margin-top:4px;'>{row.get('亞盤建議','-')}</div>
                </div>
                <div class='matrix-col'>
                    <div class='matrix-header'>真實賠率</div>
                    <div class='matrix-cell'><span>主</span><span>{row.get('主勝賠率', '-')}</span></div>
                    <div class='matrix-cell'><span>客</span><span>{row.get('客勝賠率', '-')}</span></div>
                </div>
            </div>
            
            <div class='footer-box'>
                <div><span class='tag tag-pick'>🎯 {row.get('首選推介','-')}</span></div>
                <div style='color:#888; font-size:0.75rem;'>{row.get('智能標籤','')}</div>
            </div>
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
