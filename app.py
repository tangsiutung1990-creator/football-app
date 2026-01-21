
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# ================= 語言設定 (Translations) =================
LANGUAGES = {
    "繁體中文": {
        "title": "足球AI Pro (V38.1 Eco)",
        "sidebar_filter": "🔍 篩選",
        "league_label": "聯賽:",
        "status_label": "狀態:",
        "all": "全部",
        "not_started": "未開賽",
        "live": "進行中",
        "completed": "完場",
        "data_source": "數據來源",
        "matches_count": "場次",
        "mode_desc": "模式: 省流高效 (3日範圍)",
        "load_error": "❌ 無法加載數據。請確保已運行 'run_me.py' 且生成了 CSV 文件。",
        "matrix_win_rate": "特化勝率%",
        "matrix_goals": "進球概率%",
        "matrix_odds": "賠率",
        "matrix_expected": "預期",
        "home": "主",
        "away": "客",
        "over25": "大2.5",
        "btts": "BTTS",
        "lang_label": "語言 / Language"
    },
    "简体中文": {
        "title": "足球AI Pro (V38.1 Eco)",
        "sidebar_filter": "🔍 筛选",
        "league_label": "联赛:",
        "status_label": "状态:",
        "all": "全部",
        "not_started": "未开赛",
        "live": "进行中",
        "completed": "完场",
        "data_source": "数据来源",
        "matches_count": "场次",
        "mode_desc": "模式: 省流高效 (3日范围)",
        "load_error": "❌ 无法加载数据。请确保已运行 'run_me.py' 且生成了 CSV 文件。",
        "matrix_win_rate": "特化胜率%",
        "matrix_goals": "进球概率%",
        "matrix_odds": "赔率",
        "matrix_expected": "预期",
        "home": "主",
        "away": "客",
        "over25": "大2.5",
        "btts": "BTTS",
        "lang_label": "语言 / Language"
    }
}

# ================= 設定區 =================
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
        if r <= 4: cls += " rank-top" 
        if r >= 18: cls += " rank-bot" 
        return f"<span class='{cls}'>#{r}</span>"
    except: return ""

def load_data():
    df = pd.DataFrame()
    source = "無"
    
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
        
        if '主Value' not in df.columns:
            df = pd.DataFrame() 
    except: pass

    if df.empty and os.path.exists(CSV_FILENAME):
        try:
            df = pd.read_csv(CSV_FILENAME)
            source = "Local Backup (CSV)"
        except: pass
        
    return df, source

# ================= 主程式 =================
def main():
    # 語言切換
    selected_lang = st.sidebar.selectbox("語言 / Language", list(LANGUAGES.keys()))
    t = LANGUAGES[selected_lang]

    st.title(t["title"])
    
    df, source = load_data()

    if df.empty:
        st.error(t["load_error"])
        return

    st.success(f"✅ {t['data_source']}: {source} | {t['matches_count']}: {len(df)} | {t['mode_desc']}")

    # 側邊欄篩選
    st.sidebar.header(t["sidebar_filter"])
    if '聯賽' in df.columns:
        leagues = [t["all"]] + sorted(list(set(df['聯賽'].astype(str))))
        sel_lg = st.sidebar.selectbox(t["league_label"], leagues)
        if sel_lg != t["all"]: df = df[df['聯賽'] == sel_lg]

    status_options = {
        t["all"]: "全部",
        t["not_started"]: "未開賽",
        t["live"]: "進行中",
        t["completed"]: "完場"
    }
    status_filter_label = st.sidebar.radio(t["status_label"], list(status_options.keys()))
    status_val = status_options[status_filter_label]
    
    if status_val != "全部":
        df = df[df['狀態'] == status_val]

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
        
        # Value 標籤
        val_h = f"<span class='val-badge'>💰 VALUE</span>" if str(row.get('主Value')) == '💰' else ""
        val_a = f"<span class='val-badge'>💰 VALUE</span>" if str(row.get('客Value')) == '💰' else ""
        
        inj_h = clean_pct(row.get('主傷', 0))
        inj_a = clean_pct(row.get('客傷', 0))
        inj_h_tag = f"<span class='inj-badge'>🚑 {inj_h}</span>" if inj_h > 0 else
