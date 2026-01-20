import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# ================= 設定區 =================
# 必須與 run_me.py 的設定一致
GOOGLE_SHEET_NAME = "數據上傳" 
CSV_FILENAME = "football_data_backup.csv" 

st.set_page_config(page_title="足球AI Pro (V38.1 Eco)", page_icon="⚽", layout="wide")

# ================= CSS 優化 (暗黑風格) =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    [data-testid="stSidebar"] { min-width: 200px !important; max-width: 250px !important; }
    
    .compact-card { background-color: #1a1c24; border: 1px solid #333; border-radius: 8px; padding: 10px; margin-bottom: 10px; font-family: 'Arial', sans-serif; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
    
    .match-header { display: flex; justify-content: space-between; color: #888; font-size: 0.8rem; margin-bottom: 8px; border-bottom: 1px solid #333; padding-bottom: 4px; }
    
    .content-row { display: grid; grid-template-columns: 7fr 3fr; align-items: center; margin-bottom: 10px; }
    .teams-area { text-align: left; display: flex; flex-direction: column; justify-content: center; }
    
    /* 隊名樣式 */
    .team-name { font-weight: bold; font-size: 1.15rem; color: #fff; margin-bottom: 4px; display: flex; align-items: center; flex-wrap: wrap; gap: 6px; } 
    
    /* 排名標章 */
    .rank-badge { background: #555; color: #fff; font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; font-weight: bold; border: 1px solid #777; }
    .rank-top { background: #ff9800; color: #000; border: 1px solid #ff9800; }
    .rank-bot { background: #d32f2f; color: #fff; border: 1px solid #d32f2f; }
    
    /* 走勢圓點 */
    .team-sub { font-size: 0.75rem; color: #aaa; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 2px;}
    .form-dots { display: flex; gap: 3px; align-items: center; }
    .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; border: 1px solid #000; }
    .dot-W { background-color: #00e676; }
    .dot-D { background-color: #ffeb3b; }
    .dot-L { background-color: #ff5252; }
    .dot-N { background-color: #555; }
    
    /* Value 標籤 (金色) */
    .val-badge { color: #000; background: #ffd700; font-weight: bold; font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; margin-left: 5px; box-shadow: 0 0 5px rgba(255, 215, 0, 0.5); border: 1px solid #e6c200; }

    /* 比分與 xG */
    .score-area { text-align: right; display: flex; flex-direction: column; align-items: flex-end; }
    .score-main { font-size: 2.0rem; font-weight: bold; color: #00ffea; letter-spacing: 2px; line-height: 1; }
    .xg-sub { font-size: 0.7rem; color: #888; margin-top: 4px; border: 1px solid #444; padding: 1px 4px; border-radius: 4px; background: #222; }
    
    /* 其他標籤 */
    .inj-badge { color: #ff4b4b; font-weight: bold; font-size: 0.75rem; border: 1px solid #ff4b4b; padding: 0 4px; border-radius: 3px; }
    .h2h-badge { color: #ffd700; font-weight: bold; font-size: 0.75rem; background: #333; padding: 0 4px; border-radius: 3px; }
    
    /* 數據矩陣 */
    .grid-matrix { display: grid; grid-template-columns: repeat(4, 1fr); gap: 2px; font-size: 0.75rem; margin-top: 8px; text-align: center; }
    .matrix-col { background: #222; padding: 2px; border-radius: 4px; border: 1px solid #333; display: flex; flex-direction: column; }
    .matrix-header { color: #ff9800; font-weight: bold; font-size: 0.75rem; margin-bottom: 2px; border-bottom: 1px solid #444; padding-bottom: 1px; }
    .matrix-cell { display: flex; justify-content: space-between; padding: 0 4px; align-items: center; line-height: 1.4; }
    .cell-val { color: #fff; font-weight: bold; font-size: 0.9rem; }
    .cell-val-high { color: #00ff00; font-weight: bold; font-size: 0.9rem; }
    .cell-val-zero { color: #444; font-size: 0.9rem; }
</style>
""", unsafe_allow_html=True)

# ================= 輔助函數 =================
def clean_pct(val):
    if pd.isna(val) or val == '' or str(val) == 'nan': return 0
    try:
        f = float(str(val).replace('%', ''))
        return int(f)
    except: return 0

def format_odds(val):
    try:
        f = float(val)
        if f <= 1: return "-"
        return f"{f:.2f}"
    except: return "-"

def fmt_pct_display(val, threshold=50, is_o25=False):
    v = clean_pct(val)
    if v == 0: return "<span class='cell-val-zero'>-</span>"
    css_class = "cell-val-high" if (v > threshold) else "cell-val"
    if is_o25 and v > 55: css_class = "cell-val-high"
    return f"<span class='{css_class}'>{v}%</span>"

def render_form_dots(form_str):
    if not form_str or str(form_str) == 'nan' or form_str == 'N/A' or form_str == '?????': 
        return "" 
    html = "<div class='form-dots'>"
    for char in str(form_str)[-5:]:
        cls = "dot-N"
        if char == 'W': cls = "dot-W"
        elif char == 'D': cls = "dot-D"
        elif char == 'L': cls = "dot-L"
        html += f"<span class='dot {cls}'></span>"
    html += "</div>"
    return html

def render_rank_badge(rank):
    if str(rank) == '?' or str(rank) == 'nan':
        return "<span class='rank-badge'>#?</span>"
    try:
        r = int(rank)
        cls = "rank-badge"
        if r <= 4: cls += " rank-top" # 前4名高亮
        if r >= 18: cls += " rank-bot" # 降級區警示
        return f"<span class='{cls}'>#{r}</span>"
    except: return ""

def load_data():
    df = pd.DataFrame()
    source = "無"
    
    # 1. 優先嘗試 Google Sheet
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        if os.path.exists("key.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        source = "Google Cloud"
        
        # 簡單檢查數據是否完整，如果不完整則降級到 CSV
        if '主Value' not in df.columns:
            df = pd.DataFrame() 
    except: pass

    # 2. 如果 Google Sheet 失敗或格式不對，讀取本地 CSV
    if df.empty and os.path.exists(CSV_FILENAME):
        try:
            df = pd.read_csv(CSV_FILENAME)
            source = "Local Backup (CSV)"
        except: pass
        
    return df, source

# ================= 主程式 =================
def main():
    st.title("⚽ 足球AI Pro (V38.1 Eco)")
    
    df, source = load_data()

    if df.empty:
        st.error("❌ 無法加載數據。請確保已運行 'run_me.py' 且生成了 CSV 文件。")
        return

    st.success(f"✅ 數據來源: {source} | 場次: {len(df)} | 模式: 省流高效 (3日範圍)")

    # 側邊欄篩選
    st.sidebar.header("🔍 篩選")
    if '聯賽' in df.columns:
        leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
        sel_lg = st.sidebar.selectbox("聯賽:", leagues)
        if sel_lg != "全部": df = df[df['聯賽'] == sel_lg]

    status_filter = st.sidebar.radio("狀態:", ["全部", "未開賽", "進行中", "完場"])
    if status_filter == "未開賽": df = df[df['狀態'] == '未開賽']
    elif status_filter == "進行中": df = df[df['狀態'] == '進行中']
    elif status_filter == "完場": df = df[df['狀態'] == '完場']

    # 排序：進行中 > 未開賽 > 完場
    df['sort_idx'] = df['狀態'].apply(lambda x: 0 if x == '進行中' else 1 if x=='未開賽' else 2)
    df = df.sort_values(by=['sort_idx', '時間'])

    for index, row in df.iterrows():
        # 讀取數值
        prob_h = clean_pct(row.get('主勝率', 0))
        prob_a = clean_pct(row.get('客勝率', 0))
        prob_o25 = clean_pct(row.get('大2.5', 0))
        
        score_txt = f"{row.get('主分')} - {row.get('客分')}" if str(row.get('主分')) != '' and str(row.get('主分')) != 'nan' else "VS"
        
        # 渲染標籤
        rank_h = render_rank_badge(row.get('主排名', '?'))
        rank_a = render_rank_badge(row.get('客排名', '?'))
        form_h = render_form_dots(row.get('主走勢', '?????'))
        form_a = render_form_dots(row.get('客走勢', '?????'))
        
        # Value 標籤 (只要欄位裡是 '💰' 就顯示)
        val_h = f"<span class='val-badge'>💰 VALUE</span>" if str(row.get('主Value')) == '💰' else ""
        val_a = f"<span class='val-badge'>💰 VALUE</span>" if str(row.get('客Value')) == '💰' else ""
        
        inj_h = clean_pct(row.get('主傷', 0))
        inj_a = clean_pct(row.get('客傷', 0))
        inj_h_tag = f"<span class='inj-badge'>🚑 {inj_h}</span>" if inj_h > 0 else ""
        inj_a_tag = f"<span class='inj-badge'>🚑 {inj_a}</span>" if inj_a > 0 else ""
        
        h2h_tag = f"<span class='h2h-badge'>⚔️ {row.get('H2H主')}-{row.get('H2H和')}-{row.get('H2H客')}</span>"
        xg_txt = f"xG: {row.get('xG主',0)} - {row.get('xG客',0)} ({row.get('數據源','-')})"

        # HTML 卡片構建
        card_html = f"<div class='compact-card'>"
        card_html += f"<div class='match-header'><span>{row.get('時間','')} | {row.get('聯賽','')}</span><span>{row.get('狀態','')}</span></div>"
        
        card_html += f"<div class='content-row'>"
        # 主客隊資訊
        card_html += f"<div class='teams-area'>"
        card_html += f"<div class='team-name'>{row.get('主隊','')} {rank_h} {inj_h_tag} {val_h}</div>"
        card_html += f"<div class='team-sub'>{form_h} {h2h_tag}</div>"
        card_html += f"<div class='team-name' style='margin-top:6px;'>{row.get('客隊','')} {rank_a} {inj_a_tag} {val_a}</div>"
        card_html += f"<div class='team-sub'>{form_a}</div>"
        card_html += f"</div>"
        
        # 比分與 xG
        card_html += f"<div class='score-area'><span class='score-main'>{score_txt}</span><span class='xg-sub'>{xg_txt}</span></div>"
        card_html += f"</div>"
        
        # 數據矩陣
        card_html += f"<div class='grid-matrix'>"
        card_html += f"<div class='matrix-col'><div class='matrix-header'>特化勝率%</div><div class='matrix-cell'><span class='cell-val'>主</span>{fmt_pct_display(prob_h)}</div><div class='matrix-cell'><span class='cell-val'>客</span>{fmt_pct_display(prob_a)}</div></div>"
        card_html += f"<div class='matrix-col'><div class='matrix-header'>進球概率%</div><div class='matrix-cell'><span class='cell-val'>大2.5</span>{fmt_pct_display(prob_o25, 55, True)}</div><div class='matrix-cell'><span class='cell-val'>BTTS</span>{fmt_pct_display(row.get('BTTS',0))}</div></div>"
        card_html += f"<div class='matrix-col'><div class='matrix-header'>賠率</div><div class='matrix-cell'><span class='cell-val'>主</span><span style='color:#00e5ff'>{format_odds(row.get('主賠'))}</span></div><div class='matrix-cell'><span class='cell-val'>客</span><span style='color:#00e5ff'>{format_odds(row.get('客賠'))}</span></div></div>"
        card_html += f"<div class='matrix-col'><div class='matrix-header'>預期</div><div class='matrix-cell'><span class='cell-val'>主xG</span><span class='cell-val'>{row.get('xG主')}</span></div><div class='matrix-cell'><span class='cell-val'>客xG</span><span class='cell-val'>{row.get('xG客')}</span></div></div>"
        card_html += f"</div>" # End Matrix

        card_html += f"</div>"
        st.markdown(card_html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
