import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI Pro (V24.0)", page_icon="⚽", layout="wide")

# ================= CSS 優化 (字大、緊湊) =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .compact-card { background-color: #1a1c24; border: 1px solid #333; border-radius: 8px; padding: 10px; margin-bottom: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); font-family: 'Arial', sans-serif; }
    
    .match-header { display: flex; justify-content: space-between; color: #888; font-size: 0.85rem; margin-bottom: 5px; border-bottom: 1px solid #333; padding-bottom: 3px; }
    
    .team-row { display: grid; grid-template-columns: 4fr 1fr 4fr; align-items: center; margin-bottom: 8px; }
    .team-name { font-weight: bold; font-size: 1.2rem; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; } 
    .score-box { font-size: 1.8rem; font-weight: bold; color: #00ffea; text-align: center; }
    
    /* 6欄緊湊網格 */
    .grid-matrix { display: grid; grid-template-columns: repeat(6, 1fr); gap: 2px; font-size: 0.75rem; margin-top: 5px; text-align: center; }
    .matrix-col { background: #222; padding: 2px; border-radius: 4px; border: 1px solid #333; display: flex; flex-direction: column; }
    
    /* 標題 */
    .matrix-header { color: #ff9800; font-weight: bold; font-size: 0.75rem; margin-bottom: 2px; border-bottom: 1px solid #444; padding-bottom: 1px; }
    
    /* 數據單元格 */
    .matrix-cell { display: flex; justify-content: space-between; padding: 0 4px; align-items: center; line-height: 1.4; }
    .cell-label { color: #999; font-size: 0.75rem; }
    .cell-val { color: #fff; font-weight: bold; font-size: 0.9rem; } /* 加大字體 */
    .cell-val-high { color: #00ff00; font-weight: bold; font-size: 0.9rem; }
    
    .footer-box { display: flex; justify-content: space-between; margin-top: 6px; background: #16181d; padding: 4px 8px; border-radius: 4px; align-items: center; }
    .tag-pick { background: #00b09b; color: #000; font-weight: bold; padding: 2px 6px; border-radius: 4px; font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)

# ================= 數據處理函式 =================
def clean_pct(val):
    if pd.isna(val) or val == '': return 0
    try:
        f = float(str(val).replace('%', ''))
        # V24 後端已經確保是 0-100，這裡做個防呆
        if f > 100: f = 100 
        return int(f)
    except: return 0

# ================= 主程式 =================
def main():
    st.title("⚽ 足球AI Pro (V24.0 API-Native)")
    
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if os.path.exists("key.json"): creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        else: creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
    except:
        st.error("連接失敗")
        return

    if df.empty:
        st.warning("⚠️ 暫無數據")
        return

    # === 側邊欄篩選 ===
    st.sidebar.header("🔍 篩選")
    
    # 聯賽
    if '聯賽' in df.columns:
        leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
        sel_lg = st.sidebar.selectbox("聯賽:", leagues)
        if sel_lg != "全部": df = df[df['聯賽'] == sel_lg]

    # 狀態
    status_filter = st.sidebar.radio("狀態:", ["全部", "未開賽", "進行中", "完場", "延遲/取消"])
    if status_filter == "未開賽": df = df[df['狀態'] == '未開賽']
    elif status_filter == "進行中": df = df[df['狀態'] == '進行中']
    elif status_filter == "完場": df = df[df['狀態'] == '完場']
    elif status_filter == "延遲/取消": df = df[df['狀態'].str.contains('延遲|取消')]

    # 日期
    if '時間' in df.columns:
        df['日期'] = df['時間'].apply(lambda x: str(x).split(' ')[0])
        dates = ["全部"] + sorted(list(set(df['日期'])), reverse=True) # 最近日期排前
        sel_date = st.sidebar.selectbox("日期:", dates)
        if sel_date != "全部": df = df[df['日期'] == sel_date]

    # 排序
    df['sort_idx'] = df['狀態'].apply(lambda x: 0 if x == '進行中' else 1 if x=='未開賽' else 2)
    df = df.sort_values(by=['sort_idx', '時間'])

    # === 渲染卡片 ===
    for index, row in df.iterrows():
        # 主要樣式判斷
        prob_h = clean_pct(row.get('主勝率', 0))
        prob_a = clean_pct(row.get('客勝率', 0))
        prob_o25 = clean_pct(row.get('大2.5', 0))
        
        cls_h = "cell-val-high" if prob_h > 50 else "cell-val"
        cls_a = "cell-val-high" if prob_a > 50 else "cell-val"
        cls_o25 = "cell-val-high" if prob_o25 > 55 else "cell-val"

        card_html = ""
        card_html += f"<div class='compact-card'>"
        card_html += f"<div class='match-header'><span>{row.get('時間','')} | {row.get('聯賽','')}</span><span>{row.get('狀態','')}</span></div>"
        
        card_html += f"<div class='team-row'>"
        card_html += f"<div style='text-align:right;'><div class='team-name'>{row.get('主隊','')}</div></div>"
        
        score_display = f"{row.get('主分','')} - {row.get('客分','')}" if row.get('主分') != '' else "vs"
        card_html += f"<div class='score-box'>{score_display}</div>"
        
        card_html += f"<div><div class='team-name'>{row.get('客隊','')}</div></div>"
        card_html += f"</div>"
        
        # Grid Matrix (6 Columns)
        card_html += f"<div class='grid-matrix'>"
        
        # 1. 勝率 (API)
        card_html += f"<div class='matrix-col'><div class='matrix-header'>勝率 (API)</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>主</span><span class='{cls_h}'>{prob_h}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>和</span><span class='cell-val'>{clean_pct(row.get('和局率',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>客</span><span class='{cls_a}'>{prob_a}%</span></div></div>"
        
        # 2. 亞盤 (主)
        card_html += f"<div class='matrix-col'><div class='matrix-header'>主亞盤%</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>平(0)</span><span class='cell-val'>{clean_pct(row.get('主平',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+0.5</span><span class='cell-val'>{clean_pct(row.get('主+0.5',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+1.0</span><span class='cell-val'>{clean_pct(row.get('主+1',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>-2.0</span><span class='cell-val'>{clean_pct(row.get('主-2',0))}%</span></div></div>"
        
        # 3. 亞盤 (客)
        card_html += f"<div class='matrix-col'><div class='matrix-header'>客亞盤%</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>平(0)</span><span class='cell-val'>{clean_pct(row.get('客平',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+0.5</span><span class='cell-val'>{clean_pct(row.get('客+0.5',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+1.0</span><span class='cell-val'>{clean_pct(row.get('客+1',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>-2.0</span><span class='cell-val'>{clean_pct(row.get('客-2',0))}%</span></div></div>"
        
        # 4. 全場大小
        card_html += f"<div class='matrix-col'><div class='matrix-header'>全場大小</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>大0.5</span><span class='cell-val'>{clean_pct(row.get('大0.5',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>大1.5</span><span class='cell-val'>{clean_pct(row.get('大1.5',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>大2.5</span><span class='{cls_o25}'>{prob_o25}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>大3.5</span><span class='cell-val'>{clean_pct(row.get('大3.5',0))}%</span></div></div>"
        
        # 5. 半場大小
        card_html += f"<div class='matrix-col'><div class='matrix-header'>半場大小</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>H0.5</span><span class='cell-val'>{clean_pct(row.get('HT0.5',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>H1.5</span><span class='cell-val'>{clean_pct(row.get('HT1.5',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>H2.5</span><span class='cell-val'>{clean_pct(row.get('HT2.5',0))}%</span></div></div>"
        
        # 6. 賠率/凱利
        card_html += f"<div class='matrix-col'><div class='matrix-header'>賠率/凱利</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>主賠</span><span style='color:#00e5ff;'>{row.get('主賠','-')}</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>客賠</span><span style='color:#00e5ff;'>{row.get('客賠','-')}</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>K主</span><span class='cell-val'>{clean_pct(row.get('凱利主',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>K客</span><span class='cell-val'>{clean_pct(row.get('凱利客',0))}%</span></div></div>"
        
        card_html += f"</div>" # End Grid
        
        # Footer
        advice = row.get('推介', '暫無')
        card_html += f"<div class='footer-box'><div><span class='tag-pick'>🎯 API推介: {advice}</span></div></div>"
        card_html += f"</div>"

        st.markdown(card_html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
