# 檔案名稱: app.py
import streamlit as st
import pandas as pd

# ================= 配置區 =================
# 🔥 已更新為你的新數據連結
DATA_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRhoWj63UGng_ikz6r9fs6nLSZgNxuEkheBirzlYU5L9x9eTVr1w2tQt436z8vKU1HoIm16NR38zySy/pub?output=csv"

st.set_page_config(page_title="全球重心 V86", layout="wide", page_icon="⚽")

# ================= CSS 樣式 (針對手機優化) =================
st.markdown("""
<style>
    .stApp {background-color:#0e1117; color:#e0e0e0; font-family:'Arial', sans-serif;}
    .block-container {padding-top: 1rem; padding-bottom: 5rem;} 
    .table-container {
        width: 100%; overflow-x: auto; margin-bottom: 20px;
        border: 1px solid #333; border-radius: 8px; background-color: #1e1e1e;
        -webkit-overflow-scrolling: touch; /* 讓手機滑動更順暢 */
    }
    .data-table { width: 100%; border-collapse: collapse; min-width: 1000px; text-align: center; font-size: 13px; }
    .data-table th { background-color: #262626; color: #aaa; padding: 10px; position: sticky; top: 0; z-index: 10; border-bottom: 2px solid #444; }
    .data-table td { padding: 8px; border-bottom: 1px solid #333; border-right: 1px solid #2a2a2a; color: #fff; white-space: nowrap; }
    
    .col-odds { color: #00ff7f; font-family: monospace; font-weight: bold; }
    .col-dim { color: #666; }
    .highlight-win { background-color: rgba(0, 255, 127, 0.2); color: #00ff7f !important; }
    .highlight-big { background-color: rgba(255, 75, 75, 0.2); color: #ff4b4b !important; }
    .rank-badge { background:#444; padding:2px 6px; border-radius:4px; font-size:11px; }
</style>
""", unsafe_allow_html=True)

# ================= 數據讀取 (加入 Cache 機制) =================
@st.cache_data(ttl=60)
def load_data():
    try:
        # 讀取你的 Google Sheet CSV
        return pd.read_csv(DATA_URL, on_bad_lines='skip', header=None)
    except Exception as e:
        return None

# ================= 分析邏輯 =================
def safe_val(row, idx, is_str=False):
    try:
        val = row[idx]
        if pd.isna(val) or str(val).strip() == "": return "-" if is_str else 0.0
        return str(val).strip() if is_str else float(val)
    except: return "-" if is_str else 0.0

def analyze(row):
    # 根據 CSV 欄位位置抓取數據
    h_r = safe_val(row, 4)  # 主排
    a_r = safe_val(row, 5)  # 客排
    ft_h = safe_val(row, 8) # 主勝賠率
    o25, o35 = safe_val(row, 14), safe_val(row, 15) # 大小球賠率
    
    # 計算近況分 (W=3, D=1, L=0)
    def f_sc(s): return sum([3 if c=='W' else 1 if c=='D' else 0 for c in str(s).upper()[-6:]])
    h_s = f_sc(row[6]) if len(row)>6 else 0
    a_s = f_sc(row[7]) if len(row)>7 else 0
    
    # 簡單預測公式
    power = (a_r - h_r) + ((h_s - a_s) * 1.5)
    is_home = (ft_h > 0 and ft_h < 1.45) or (power > 6)
    is_big = (o35 > 0 and o35 < 2.25) or (o25 > 0 and o25 < 1.75)
    return is_home, is_big

# ================= 主程式 =================
st.markdown("<h3 style='text-align:center; margin-bottom:10px;'>📊 賽事分析 V86</h3>", unsafe_allow_html=True)

df = load_data()

if df is not None:
    # --- 1. 簡單篩選器 (手機救星) ---
    with st.expander("🔍 篩選與設定", expanded=False):
        show_only_rec = st.checkbox("只顯示有推薦 (重心/大球)", value=False)
        
        # 自動抓取 CSV 第 2 欄 (Index 1) 作為聯賽名稱
        try:
            all_leagues = sorted(list(set([str(x) for x in df[1] if str(x) not in ['nan', '聯賽', '-']])))
            selected_leagues = st.multiselect("選擇聯賽", all_leagues, default=[])
        except:
            selected_leagues = []

    # --- 2. 構建 HTML 表格 ---
    html = """<div class="table-container"><table class="data-table"><thead><tr>
    <th>時間</th><th>聯賽</th><th>主隊</th><th>客隊</th><th>主排</th><th>客排</th><th>主近</th><th>客近</th>
    <th>主勝</th><th>和</th><th>客勝</th><th>半主</th><th>半和</th><th>半客</th>
    <th>大2.5</th><th>大3.5</th><th>細2.5</th><th>細3.5</th></tr></thead><tbody>"""

    count = 0
    for i, row in df.iterrows():
        # 跳過標題行
        if str(row[0]) in ["時間", "日期", "-"] or pd.isna(row[2]): continue
        
        # 聯賽篩選
        league_name = str(row[1])
        if selected_leagues and league_name not in selected_leagues: continue

        home_good, big_good = analyze(row)
        
        # 只顯示推薦
        if show_only_rec and not (home_good or big_good): continue

        c_hw = "highlight-win" if home_good else "col-odds"
        c_big = "highlight-big" if big_good else "col-odds"
        v = lambda x: safe_val(row, x, True)
        
        html += f"""<tr>
        <td style="color:#888;">{v(0)}</td> <td style="color:#aaa;">{v(1)}</td>
        <td style="text-align:left;font-weight:bold;">{v(2)}</td> <td style="text-align:left;font-weight:bold;">{v(3)}</td>
        <td><span class="rank-badge">{v(4)}</span></td> <td><span class="rank-badge">{v(5)}</span></td>
        <td style="font-size:11px;">{v(6)}</td> <td style="font-size:11px;">{v(7)}</td>
        <td class="{c_hw}">{v(8)}</td> <td class="col-odds">{v(9)}</td> <td class="col-odds">{v(10)}</td>
        <td class="col-dim">{v(11)}</td> <td class="col-dim">{v(12)}</td> <td class="col-dim">{v(13)}</td>
        <td class="{c_big}">{v(14)}</td> <td class="{c_big}">{v(15)}</td> <td class="col-dim">{v(16)}</td> <td class="col-dim">{v(17)}</td>
        </tr>"""
        count += 1
        
    html += "</tbody></table></div>"
    
    st.caption(f"共顯示 {count} 場賽事")
    st.markdown(html, unsafe_allow_html=True)

else:
    st.error("無法讀取數據，請檢查：1. Google Sheet 是否已發佈為 CSV。 2. 連結是否正確。")