# 檔案名稱: app.py
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz # 用來處理時區

# ================= 配置區 =================
DATA_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRhoWj63UGng_ikz6r9fs6nLSZgNxuEkheBirzlYU5L9x9eTVr1w2tQt436z8vKU1HoIm16NR38zySy/pub?output=csv"

st.set_page_config(page_title="足球AI 智能完場版", layout="wide", page_icon="⚽")

# ================= CSS 優化 =================
st.markdown("""
<style>
    .stApp {background-color:#0e1117; color:#e0e0e0; font-family:'Arial', sans-serif;}
    .block-container {padding-top: 1rem; padding-bottom: 5rem;} 
    
    .table-container {
        width: 100%; overflow-x: auto; margin-bottom: 20px;
        border: 1px solid #333; border-radius: 8px; background-color: #1e1e1e;
    }
    .data-table { width: 100%; border-collapse: collapse; min-width: 900px; text-align: center; font-size: 13px; }
    
    .data-table th { background-color: #262626; color: #aaa; padding: 12px 8px; border-bottom: 2px solid #444; white-space: nowrap; }
    .data-table td { padding: 8px; border-bottom: 1px solid #333; border-right: 1px solid #2a2a2a; color: #fff; }
    
    /* 狀態標籤 */
    .status-playing { color: #00ff00; font-weight: bold; animation: pulse 2s infinite; }
    .status-ended { color: #666; font-style: italic; }
    .row-ended td { color: #666 !important; } /* 完場整行變灰 */

    /* 特別顏色 */
    .col-goals { color: #00bfff; font-weight: bold; font-family: monospace; font-size: 1.1em; white-space: nowrap; } 
    .highlight-win { background-color: rgba(0, 255, 127, 0.2); color: #00ff7f !important; font-weight:bold; } 
    .highlight-big { background-color: rgba(255, 75, 75, 0.2); color: #ff4b4b !important; font-weight:bold; } 
    
    .rank-badge { background:#444; padding:2px 6px; border-radius:4px; font-size:11px; white-space: nowrap;}
    .league-tag { font-size:10px; color:#aaa; border:1px solid #444; padding:2px 4px; border-radius:4px; white-space: nowrap;}

    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
</style>
""", unsafe_allow_html=True)

# ================= 數據讀取 =================
@st.cache_data(ttl=60)
def load_data():
    try:
        return pd.read_csv(DATA_URL, on_bad_lines='skip', header=None)
    except: return None

# ================= 輔助功能 =================
def safe_val(row, idx):
    try:
        val = row[idx]
        if pd.isna(val) or str(val).strip() == "": return 0.0
        return float(val)
    except: return 0.0

# 🕒 新增：判斷比賽狀態
def get_match_status(date_str):
    try:
        # 假設 CSV 時間格式係 "01/06 04:00" (月/日 時:分)
        # 我哋需要加上年份 (假設係 2026)
        current_year = datetime.now().year
        match_time_str = f"{current_year}/{date_str}" 
        
        # 轉換成時間物件
        match_dt = datetime.strptime(match_time_str, "%Y/%m/%d %H:%M")
        
        # 設定為香港時間 (UTC+8) - 因為 Streamlit Server 係 UTC
        tz_hk = pytz.timezone('Asia/Hong_Kong')
        match_dt = tz_hk.localize(match_dt) # 假設 CSV 時間係香港時間
        
        now = datetime.now(tz_hk)
        
        # 判斷
        diff = (now - match_dt).total_seconds() / 60 # 分鐘差距
        
        if diff < 0:
            return "upcoming", "未開賽"
        elif 0 <= diff <= 120: # 開波 2 小時內
            return "playing", "⚽ 進行中"
        else:
            return "ended", "🛑 已完場"
    except:
        return "unknown", "-"

def analyze_match(row):
    h_gf = safe_val(row, 11) 
    h_ga = safe_val(row, 12)
    a_gf = safe_val(row, 13)
    a_ga = safe_val(row, 14)
    
    def f_sc(s): return sum([3 if c=='W' else 1 if c=='D' else 0 for c in str(s).upper()[-6:]])
    h_form = f_sc(row[6]) if len(row)>6 else 0
    a_form = f_sc(row[7]) if len(row)>7 else 0

    rec_home = False
    rec_big = False
    
    h_net = h_gf - h_ga
    a_net = a_gf - a_ga
    if (h_net > a_net + 0.5) and (h_form >= a_form):
        rec_home = True

    exp_goals = (h_gf + a_ga)/2 + (a_gf + h_ga)/2
    if exp_goals >= 2.6:
        rec_big = True
        
    return rec_home, rec_big, exp_goals

# ================= 主程式 =================
st.markdown("<h3 style='text-align:center;'>⚽ 足球數據中心</h3>", unsafe_allow_html=True)

df = load_data()

if df is not None:
    # --- 篩選 ---
    with st.expander("🔍 顯示設定", expanded=False):
        col1, col2 = st.columns(2)
        with col1: show_rec_only = st.checkbox("只顯示推薦 (重心)", value=False)
        with col2: hide_ended = st.checkbox("隱藏已完場賽事", value=False)
        
        try:
            leagues = sorted(list(set([str(x) for x in df[1] if str(x) not in ['nan', '聯賽', '-']])))
            sel_leagues = st.multiselect("選擇聯賽", leagues, default=[])
        except: sel_leagues = []

    # --- 構建表格 HTML ---
    html = """<div class="table-container"><table class="data-table"><thead><tr>
    <th style="width:50px;">狀態</th> <th style="width:50px;">時間</th>
    <th style="width:40px;">聯賽</th>
    <th style="width:130px;">主隊</th>
    <th style="width:130px;">客隊</th>
    <th style="color:#00bfff;">主 入/失</th>
    <th style="color:#00bfff;">客 入/失</th>
    <th>預測結果</th>
    <th>期望入球</th>
    </tr></thead><tbody>"""

    count = 0
    for i, row in df.iterrows():
        if str(row[0]) in ["時間", "日期", "-"] or pd.isna(row[2]): continue
        if sel_leagues and str(row[1]) not in sel_leagues: continue

        # 取得狀態
        status_code, status_text = get_match_status(row[0])
        
        # 如果用戶揀咗「隱藏完場」
        if hide_ended and status_code == "ended": continue

        # 分析
        is_h, is_b, exp_g = analyze_match(row)
        if show_rec_only and not (is_h or is_b): continue

        # 樣式處理
        c_res = ""
        txt_res = "-"
        row_class = "" # 用來將整行變灰
        
        if status_code == "ended":
            row_class = "row-ended"
            status_html = f"<span class='status-ended'>{status_text}</span>"
        elif status_code == "playing":
            status_html = f"<span class='status-playing'>{status_text}</span>"
        else:
            status_html = f"<span style='color:#888'>{status_text}</span>"

        if is_h: 
            c_res = "highlight-win"
            txt_res = "🏆 主勝"
        if is_b:
            c_res = "highlight-big"
            txt_res = "🔥 大球" if not is_h else "🏆主+大"
            
        v = lambda x: str(row[x]).strip() if not pd.isna(row[x]) else "-"
        
        h_stats = f"{safe_val(row,11):.1f} / {safe_val(row,12):.1f}"
        a_stats = f"{safe_val(row,13):.1f} / {safe_val(row,14):.1f}"

        html += f"""<tr class="{row_class}">
        <td>{status_html}</td>
        <td style="color:#888; font-size:12px;">{v(0)}</td>
        <td><span class="league-tag">{v(1)}</span></td>
        <td style="text-align:left; font-weight:bold; white-space:normal; line-height:1.2;">{v(2)}</td>
        <td style="text-align:left; font-weight:bold; white-space:normal; line-height:1.2;">{v(3)}</td>
        <td class="col-goals">{h_stats}</td>
        <td class="col-goals">{a_stats}</td>
        <td class="{c_res}">{txt_res}</td>
        <td style="color:#888;">{exp_g:.2f}球</td>
        </tr>"""
        count += 1
        
    html += "</tbody></table></div>"
    st.markdown(html, unsafe_allow_html=True)
    st.caption(f"顯示 {count} 場賽事 | 💡 提示：超過 2 小時的比賽會自動標示為完場")

else:
    st.error("讀取中... 請稍後刷新")
