import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz

# ================= 配置區 =================
# 請確保這是你的 CSV 發布連結
DATA_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRhoWj63UGng_ikz6r9fs6nLSZgNxuEkheBirzlYU5L9x9eTVr1w2tQt436z8vKU1HoIm16NR38zySy/pub?output=csv"

st.set_page_config(page_title="足球AI 智能完場版", layout="wide", page_icon="⚽")

# ================= CSS 優化 (手機窄身設計 + 完場變暗) =================
st.markdown("""
<style>
    .stApp {background-color:#0e1117; color:#e0e0e0; font-family:'Arial', sans-serif;}
    .block-container {padding-top: 0.5rem; padding-bottom: 2rem;} 
    
    /* 表格容器 */
    .table-container {
        width: 100%; 
        overflow-x: auto; 
        margin-bottom: 20px;
        border: 1px solid #333; 
        border-radius: 8px; 
        background-color: #1e1e1e;
    }
    
    /* 表格本體 */
    .data-table { 
        width: 100%; 
        border-collapse: collapse; 
        white-space: nowrap; /* 保持單行 */
        font-size: 13px;
        text-align: center;
    }
    
    .data-table th { background-color: #262626; color: #aaa; padding: 10px 6px; border-bottom: 2px solid #444; }
    .data-table td { padding: 8px 4px; border-bottom: 1px solid #333; color: #ddd; }
    
    /* --- 狀態特效 --- */
    .status-playing { 
        color: #00ff00; 
        font-weight: bold; 
        animation: pulse 1.5s infinite; 
        border: 1px solid #00ff00;
        padding: 2px 6px;
        border-radius: 10px;
        font-size: 10px;
    }
    
    .status-upcoming {
        color: #aaa;
        background: #333;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 10px;
    }

    /* --- 完場處理 (灰色 + 半透明 + 黑白濾鏡) --- */
    .row-ended { 
        filter: grayscale(100%); 
        opacity: 0.5; 
        background-color: #161616;
    }
    .row-ended td { color: #555 !important; }

    /* --- 重點顏色 --- */
    .col-goals { color: #00bfff; font-family: monospace; font-weight: bold; } 
    .highlight-win { background-color: rgba(0, 255, 127, 0.15); color: #00ff7f !important; font-weight:bold; } 
    .highlight-big { background-color: rgba(255, 75, 75, 0.15); color: #ff4b4b !important; font-weight:bold; } 
    .league-tag { font-size:10px; color:#888; border:1px solid #333; padding:1px 3px; border-radius:3px; }

    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
</style>
""", unsafe_allow_html=True)

# ================= 數據讀取 =================
@st.cache_data(ttl=60)
def load_data():
    try:
        # header=None 代表我們用 index 0, 1, 2... 來讀取
        return pd.read_csv(DATA_URL, on_bad_lines='skip', header=None)
    except: return None

# ================= 輔助功能 =================
def safe_val(row, idx):
    try:
        val = row[idx]
        if pd.isna(val) or str(val).strip() == "": return 0.0
        return float(val)
    except: return 0.0

# 🕒 智能時間識別
def get_match_status(date_str):
    try:
        # 取得目前香港時間
        tz_hk = pytz.timezone('Asia/Hong_Kong')
        now = datetime.now(tz_hk)
        
        # 處理年份問題 (假設現在是 1月，但讀到 12月數據，年份應減 1)
        current_year = now.year
        match_month = int(date_str.split('/')[0])
        if now.month == 1 and match_month == 12:
            current_year -= 1
        
        match_time_str = f"{current_year}/{date_str}" 
        match_dt = datetime.strptime(match_time_str, "%Y/%m/%d %H:%M")
        match_dt = tz_hk.localize(match_dt) 
        
        # 計算差距 (分鐘)
        diff_minutes = (now - match_dt).total_seconds() / 60
        
        if diff_minutes < 0:
            return "upcoming", "未開賽"
        elif 0 <= diff_minutes <= 125: # 比賽中 (包含補時)
            return "playing", "進行中"
        else:
            return "ended", "完"
    except:
        return "unknown", "-"

def analyze_match(row):
    h_gf = safe_val(row, 11) 
    h_ga = safe_val(row, 12)
    a_gf = safe_val(row, 13)
    a_ga = safe_val(row, 14)
    
    # 計算近況分
    def f_sc(s): return sum([3 if c=='W' else 1 if c=='D' else 0 for c in str(s).upper()[-6:]])
    h_form = f_sc(row[6]) if len(row)>6 else 0
    a_form = f_sc(row[7]) if len(row)>7 else 0

    rec_home = False
    rec_big = False
    
    # 簡單分析邏輯
    h_net = h_gf - h_ga
    a_net = a_gf - a_ga
    if (h_net > a_net + 0.3) and (h_form >= a_form):
        rec_home = True

    exp_goals = (h_gf + a_ga)/2 + (a_gf + h_ga)/2
    if exp_goals >= 2.7:
        rec_big = True
        
    return rec_home, rec_big, exp_goals

# ================= 主程式 =================
st.markdown("<h4 style='text-align:center; margin-bottom:10px;'>⚽ 足球智能看板</h4>", unsafe_allow_html=True)

df = load_data()

if df is not None:
    # --- 控制台 (Expander 收埋佢，慳位) ---
    with st.expander("⚙️ 篩選與設定", expanded=False):
        col1, col2 = st.columns(2)
        with col1: show_rec_only = st.checkbox("只看重心 (⭐)", value=False)
        with col2: hide_ended = st.checkbox("隱藏已完場", value=False)
        
        try:
            # 取得聯賽列表
            leagues = sorted(list(set([str(x) for x in df[1] if str(x) not in ['nan', '聯賽', '-']])))
            sel_leagues = st.multiselect("聯賽過濾", leagues, default=[])
        except: sel_leagues = []

    # --- HTML 表頭 ---
    # 注意：這裡新增了「比分」欄位
    html = """<div class="table-container"><table class="data-table"><thead><tr>
    <th style="width:40px;">狀態</th>
    <th style="width:40px;">時間</th>
    <th style="width:40px;">聯賽</th>
    <th style="text-align:right;">主隊</th>
    <th style="width:30px;">比分</th>
    <th style="text-align:left;">客隊</th>
    <th style="color:#00bfff;">數據(攻/防)</th>
    <th>預測</th>
    </tr></thead><tbody>"""

    count = 0
    for i, row in df.iterrows():
        # 跳過標題行
        if str(row[0]) in ["時間", "日期", "-"] or pd.isna(row[2]): continue
        if sel_leagues and str(row[1]) not in sel_leagues: continue

        # 1. 時間狀態判斷
        status_code, status_text = get_match_status(row[0])
        
        if hide_ended and status_code == "ended": continue

        # 2. 分析
        is_h, is_b, exp_g = analyze_match(row)
        if show_rec_only and not (is_h or is_b): continue

        # 3. 樣式變數
        row_class = ""
        status_html = ""
        
        if status_code == "ended":
            row_class = "row-ended"
            status_html = f"<span style='color:#666; font-size:10px;'>{status_text}</span>"
        elif status_code == "playing":
            status_html = f"<span class='status-playing'>{status_text}</span>"
        else: # upcoming
            status_html = f"<span class='status-upcoming'>{row[0].split(' ')[1]}</span>" # 只顯示時間

        # 4. 比分顯示 (預留位置)
        # 假設你的 Sheet 第 15 欄 (index 14) 是主隊分，16 欄 (index 15) 是客隊分
        # 如果目前沒有數據，就顯示 "vs"
        try:
            score_home = str(row[14]).replace("nan", "").split(".")[0] # 去小數點
            score_away = str(row[15]).replace("nan", "").split(".")[0]
            
            if score_home and score_away and score_home != "" and score_away != "":
                score_display = f"<span style='color:#fff; font-weight:bold;'>{score_home}-{score_away}</span>"
            else:
                score_display = "<span style='color:#444;'>vs</span>"
        except:
            score_display = "<span style='color:#444;'>vs</span>"

        # 5. 預測結果顯示
        res_badges = []
        if is_h: res_badges.append("<span class='highlight-win'>主勝</span>")
        if is_b: res_badges.append("<span class='highlight-big'>大球</span>")
        res_html = " ".join(res_badges) if res_badges else "<span style='color:#333'>-</span>"

        # 6. 數據顯示 (簡化為一行: 主攻/主防 vs 客攻/客防)
        # 為了手機版面，我們精簡顯示
        h_stats = f"{safe_val(row,11):.1f}"
        a_stats = f"{safe_val(row,13):.1f}"
        
        # 組裝 HTML row
        html += f"""<tr class="{row_class}">
        <td>{status_html}</td>
        <td style="color:#888; font-size:11px;">{row[0].split(' ')[0]}</td>
        <td><span class="league-tag">{row[1]}</span></td>
        <td style="text-align:right; font-weight:bold; color:#ddd;">{row[2]}</td>
        <td>{score_display}</td>
        <td style="text-align:left; font-weight:bold; color:#ddd;">{row[3]}</td>
        <td style="font-family:monospace; font-size:11px; color:#aaa;">{h_stats} v {a_stats}</td>
        <td>{res_html}</td>
        </tr>"""
        count += 1
        
    html += "</tbody></table></div>"
    st.markdown(html, unsafe_allow_html=True)
    
    # 底部顯示最後更新
    hk_now = datetime.now(pytz.timezone('Asia/Hong_Kong')).strftime("%H:%M")
    st.caption(f"最後更新: {hk_now} | 賽事總數: {count}")

else:
    st.info("數據載入中，請稍候...")