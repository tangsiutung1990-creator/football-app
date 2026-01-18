import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import math

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI Pro (V23.0)", page_icon="⚽", layout="wide")

# ================= CSS 優化 (更緊湊，字更大) =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .compact-card { background-color: #1a1c24; border: 1px solid #333; border-radius: 8px; padding: 10px; margin-bottom: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); font-family: 'Arial', sans-serif; }
    .match-header { display: flex; justify-content: space-between; color: #888; font-size: 0.8rem; margin-bottom: 6px; border-bottom: 1px solid #333; padding-bottom: 3px; }
    .team-row { display: grid; grid-template-columns: 4fr 1fr 4fr; align-items: center; margin-bottom: 8px; }
    .team-name { font-weight: bold; font-size: 1.15rem; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; } 
    .team-meta { font-size: 0.75rem; color: #aaa; }
    .score-box { font-size: 1.6rem; font-weight: bold; color: #00ffea; text-align: center; }
    
    /* 6欄緊湊網格 - 極致壓縮空間 */
    .grid-matrix { display: grid; grid-template-columns: repeat(6, 1fr); gap: 3px; font-size: 0.75rem; margin-top: 6px; text-align: center; }
    .matrix-col { background: #222; padding: 2px; border-radius: 4px; border: 1px solid #333; display: flex; flex-direction: column; justify-content: flex-start; }
    
    /* 標題字體加大，底部線條更細 */
    .matrix-header { color: #ff9800; font-weight: bold; font-size: 0.75rem; margin-bottom: 2px; border-bottom: 1px solid #444; padding-bottom: 1px; white-space: nowrap; overflow: hidden; }
    
    /* 數據行：收窄左右 padding */
    .matrix-cell { display: flex; justify-content: space-between; padding: 0 4px; align-items: center; line-height: 1.3; }
    .cell-label { color: #999; font-size: 0.75rem; }
    .cell-val { color: #fff; font-weight: bold; font-size: 0.85rem; } /* 數值字體加大 */
    .cell-val-high { color: #00ff00; font-weight: bold; font-size: 0.85rem; }
    
    .footer-box { display: flex; justify-content: space-between; margin-top: 6px; background: #16181d; padding: 4px 8px; border-radius: 4px; align-items: center; }
    .tag { font-size: 0.7rem; padding: 1px 5px; border-radius: 3px; background: #333; color: #ddd; margin-left: 3px; }
    .tag-pick { background: #00b09b; color: #000; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ================= 數據處理函式 =================
def clean_pct(val):
    if pd.isna(val) or val == '': return 0.0
    try:
        s = str(val).replace('%', '').strip()
        f = float(s)
        # 修復 "5490%" 問題：如果數值大於 100，強制除以 100 (假設是小數點位移錯誤)
        if f > 100: f = f / 100
        # 再次檢查，如果還大於 100 (例如 5490 -> 54.9 -> 正常，但如果原數是 54900)，保底處理
        if f > 100: f = 99.9 
        # 如果是小數 (例如 0.75)，轉為 75
        if f < 1.0 and f > 0: return f * 100
        return f
    except: return 0.0

def get_form_html(form_str):
    if pd.isna(form_str) or str(form_str) in ['N/A', '?????']: return "-"
    html = ""
    for char in str(form_str).strip()[-5:]:
        color = "#28a745" if char.upper()=='W' else "#ffc107" if char.upper()=='D' else "#dc3545"
        html += f"<span style='color:{color}; font-weight:bold; margin-left:1px;'>{char}</span>"
    return html

# ================= 主程式 =================
def main():
    st.title("⚽ 足球AI Pro (V23.0 賽馬會版)")
    
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

    # === 側邊欄篩選 ===
    st.sidebar.header("🔍 篩選")
    
    # 聯賽
    if '聯賽' in df.columns:
        leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
        sel_lg = st.sidebar.selectbox("聯賽:", leagues)
        if sel_lg != "全部": df = df[df['聯賽'] == sel_lg]

    # 狀態 (包含延遲/取消)
    status_filter = st.sidebar.radio("狀態:", ["全部", "未開賽", "進行中", "完場", "延遲/取消"])
    if status_filter == "未開賽": df = df[df['狀態'] == '未開賽']
    elif status_filter == "進行中": df = df[df['狀態'] == '進行中']
    elif status_filter == "完場": df = df[df['狀態'] == '完場']
    elif status_filter == "延遲/取消": df = df[df['狀態'].str.contains('延遲|取消')]

    # 日期 (排序)
    if '時間' in df.columns:
        df['日期'] = df['時間'].apply(lambda x: str(x).split(' ')[0])
        dates = ["全部"] + sorted(list(set(df['日期'])))
        sel_date = st.sidebar.selectbox("日期:", dates)
        if sel_date != "全部": df = df[df['日期'] == sel_date]

    # 排序：進行中 > 未開賽 > 完場
    df['sort_idx'] = df['狀態'].apply(lambda x: 0 if x == '進行中' else 1 if x=='未開賽' else 2)
    df = df.sort_values(by=['sort_idx', '時間'])

    for index, row in df.iterrows():
        # 讀取主要數據
        prob_h = clean_pct(row.get('主勝率', 0))
        prob_a = clean_pct(row.get('客勝率', 0))
        prob_o25 = clean_pct(row.get('大球率2.5', 0))
        
        cls_h = "cell-val-high" if prob_h > 50 else "cell-val"
        cls_a = "cell-val-high" if prob_a > 50 else "cell-val"
        cls_o25 = "cell-val-high" if prob_o25 > 55 else "cell-val"

        # 構建 HTML 字串 (無縮排，單行拼接)
        card_html = ""
        card_html += f"<div class='compact-card'>"
        # Header
        card_html += f"<div class='match-header'><span>{row.get('時間','')} | {row.get('聯賽','')}</span><span>{row.get('狀態','')}</span></div>"
        
        # Teams & Score
        card_html += f"<div class='team-row'>"
        card_html += f"<div style='text-align:right;'><div class='team-name'>{row.get('主隊','')}</div><div class='team-meta'>#{row.get('主排名','-')} {get_form_html(row.get('主近況'))}</div></div>"
        card_html += f"<div class='score-box'>{row.get('主分','')} - {row.get('客分','')}</div>"
        card_html += f"<div><div class='team-name'>{row.get('客隊','')}</div><div class='team-meta'>#{row.get('客排名','-')} {get_form_html(row.get('客近況'))}</div></div>"
        card_html += f"</div>"
        
        # Grid Matrix (6 Columns)
        card_html += f"<div class='grid-matrix'>"
        
        # Col 1: 1x2
        card_html += f"<div class='matrix-col'><div class='matrix-header'>勝率</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>主</span><span class='{cls_h}'>{prob_h:.0f}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>和</span><span class='cell-val'>{clean_pct(row.get('和局率',0)):.0f}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>客</span><span class='{cls_a}'>{prob_a:.0f}%</span></div></div>"
        
        # Col 2: 亞盤主
        card_html += f"<div class='matrix-col'><div class='matrix-header'>主亞盤%</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>平(0)</span><span class='cell-val'>{clean_pct(row.get('主平手',0)):.0f}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+0.5</span><span class='cell-val'>{clean_pct(row.get('主+0.5',0)):.0f}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+1.0</span><span class='cell-val'>{clean_pct(row.get('主+1',0)):.0f}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+2.0</span><span class='cell-val'>{clean_pct(row.get('主+2',0)):.0f}%</span></div></div>"
        
        # Col 3: 亞盤客
        card_html += f"<div class='matrix-col'><div class='matrix-header'>客亞盤%</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>平(0)</span><span class='cell-val'>{clean_pct(row.get('客平手',0)):.0f}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+0.5</span><span class='cell-val'>{clean_pct(row.get('客+0.5',0)):.0f}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+1.0</span><span class='cell-val'>{clean_pct(row.get('客+1',0)):.0f}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+2.0</span><span class='cell-val'>{clean_pct(row.get('客+2',0)):.0f}%</span></div></div>"
        
        # Col 4: 全場大小 (新增 0.5/1.5)
        card_html += f"<div class='matrix-col'><div class='matrix-header'>全場大小</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>大0.5</span><span class='cell-val'>{clean_pct(row.get('大球率0.5',0)):.0f}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>大1.5</span><span class='cell-val'>{clean_pct(row.get('大球率1.5',0)):.0f}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>大2.5</span><span class='{cls_o25}'>{prob_o25:.0f}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>大3.5</span><span class='cell-val'>{clean_pct(row.get('大球率3.5',0)):.0f}%</span></div></div>"
        
        # Col 5: 半場大小
        card_html += f"<div class='matrix-col'><div class='matrix-header'>半場大小</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>H0.5</span><span class='cell-val'>{clean_pct(row.get('HT0.5',0)):.0f}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>H1.5</span><span class='cell-val'>{clean_pct(row.get('HT1.5',0)):.0f}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>H2.5</span><span class='cell-val'>{clean_pct(row.get('HT2.5',0)):.0f}%</span></div></div>"
        
        # Col 6: 凱利/賠率
        card_html += f"<div class='matrix-col'><div class='matrix-header'>凱利/賠率</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>K主</span><span class='cell-val'>{clean_pct(row.get('凱利主',0)):.0f}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>K客</span><span class='cell-val'>{clean_pct(row.get('凱利客',0)):.0f}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>BTTS</span><span class='cell-val'>{clean_pct(row.get('BTTS率',0)):.0f}%</span></div></div>"
        
        card_html += f"</div>" # End Grid
        
        # Footer
        card_html += f"<div class='footer-box'><div><span class='tag tag-pick'>🎯 {row.get('首選推介','-')}</span></div><div style='color:#888; font-size:0.75rem;'>{row.get('智能標籤','')}</div></div>"
        card_html += f"</div>"

        st.markdown(card_html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
