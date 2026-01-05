# 檔案名稱: app.py
import streamlit as st
import pandas as pd

# ================= 配置區 =================
# 請確認這條 CSV Link 是正確的
DATA_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRhoWj63UGng_ikz6r9fs6nLSZgNxuEkheBirzlYU5L9x9eTVr1w2tQt436z8vKU1HoIm16NR38zySy/pub?output=csv"

st.set_page_config(page_title="足球AI 攻防數據版", layout="wide", page_icon="⚽")

# ================= CSS 優化 (手機版更易睇) =================
st.markdown("""
<style>
    .stApp {background-color:#0e1117; color:#e0e0e0; font-family:'Arial', sans-serif;}
    .block-container {padding-top: 1rem; padding-bottom: 5rem;} 
    
    /* 表格容器 */
    .table-container {
        width: 100%; overflow-x: auto; margin-bottom: 20px;
        border: 1px solid #333; border-radius: 8px; background-color: #1e1e1e;
    }
    .data-table { width: 100%; border-collapse: collapse; min-width: 900px; text-align: center; font-size: 13px; }
    
    /* 表頭固定 */
    .data-table th { background-color: #262626; color: #aaa; padding: 12px 8px; border-bottom: 2px solid #444; white-space: nowrap; }
    
    /* 數據格 */
    .data-table td { padding: 8px; border-bottom: 1px solid #333; border-right: 1px solid #2a2a2a; color: #fff; white-space: nowrap; }
    
    /* 特別顏色 */
    .col-goals { color: #00bfff; font-weight: bold; font-family: monospace; font-size: 1.1em; } /* 藍色顯示攻防 */
    .highlight-win { background-color: rgba(0, 255, 127, 0.2); color: #00ff7f !important; font-weight:bold; } /* 綠色主勝 */
    .highlight-big { background-color: rgba(255, 75, 75, 0.2); color: #ff4b4b !important; font-weight:bold; } /* 紅色大球 */
    
    .rank-badge { background:#444; padding:2px 6px; border-radius:4px; font-size:11px; }
    .league-tag { font-size:10px; color:#aaa; border:1px solid #444; padding:2px 4px; border-radius:4px; }
</style>
""", unsafe_allow_html=True)

# ================= 數據讀取 =================
@st.cache_data(ttl=60)
def load_data():
    try:
        return pd.read_csv(DATA_URL, on_bad_lines='skip', header=None)
    except: return None

# ================= 智能分析 (攻防版) =================
def safe_val(row, idx):
    try:
        val = row[idx]
        if pd.isna(val) or str(val).strip() == "": return 0.0
        return float(val)
    except: return 0.0

def analyze_match(row):
    # 讀取 CSV 欄位 (根據 football.py 的輸出順序)
    # Col 11=主攻, 12=主防, 13=客攻, 14=客防
    h_gf = safe_val(row, 11) 
    h_ga = safe_val(row, 12)
    a_gf = safe_val(row, 13)
    a_ga = safe_val(row, 14)
    
    # 近況分數 (作為輔助)
    def f_sc(s): return sum([3 if c=='W' else 1 if c=='D' else 0 for c in str(s).upper()[-6:]])
    h_form = f_sc(row[6]) if len(row)>6 else 0
    a_form = f_sc(row[7]) if len(row)>7 else 0

    rec_home = False
    rec_big = False
    
    # --- 預測公式 ---
    # 1. 主勝：主隊淨勝球能力 明顯高於 客隊
    h_net = h_gf - h_ga
    a_net = a_gf - a_ga
    if (h_net > a_net + 0.5) and (h_form >= a_form):
        rec_home = True

    # 2. 大球：兩隊防守都差，或者攻力超強
    # 預期入球 = (主攻+客防)/2 + (客攻+主防)/2
    exp_goals = (h_gf + a_ga)/2 + (a_gf + h_ga)/2
    
    if exp_goals >= 2.6: # 門檻：預期 2.6 球以上
        rec_big = True
        
    return rec_home, rec_big, exp_goals

# ================= 主程式 =================
st.markdown("<h3 style='text-align:center;'>⚽ 足球數據中心 (V99)</h3>", unsafe_allow_html=True)

df = load_data()

if df is not None:
    # --- 篩選 ---
    with st.expander("🔍 聯賽過濾", expanded=False):
        show_rec_only = st.checkbox("只顯示推薦場次", value=False)
        try:
            leagues = sorted(list(set([str(x) for x in df[1] if str(x) not in ['nan', '聯賽', '-']])))
            sel_leagues = st.multiselect("選擇聯賽", leagues, default=[])
        except: sel_leagues = []

    # --- 構建表格 HTML (重點修改了這裡的 Headers) ---
    html = """<div class="table-container"><table class="data-table"><thead><tr>
    <th style="width:50px;">時間</th>
    <th style="width:50px;">聯賽</th>
    <th>主隊</th>
    <th>客隊</th>
    <th>排名</th>
    <th style="color:#00bfff;">主 入/失</th> <th style="color:#00bfff;">客 入/失</th> <th>預測結果</th>
    <th>期望入球</th>
    </tr></thead><tbody>"""

    count = 0
    for i, row in df.iterrows():
        if str(row[0]) in ["時間", "日期", "-"] or pd.isna(row[2]): continue
        if sel_leagues and str(row[1]) not in sel_leagues: continue

        # 分析
        is_h, is_b, exp_g = analyze_match(row)
        
        if show_rec_only and not (is_h or is_b): continue

        # 樣式與數據
        c_res = ""
        txt_res = "-"
        if is_h: 
            c_res = "highlight-win"
            txt_res = "🏆 主勝"
        if is_b:
            c_res = "highlight-big"
            txt_res = "🔥 大球" if not is_h else "🏆主+大"
            
        v = lambda x: str(row[x]).strip() if not pd.isna(row[x]) else "-"
        
        # 組合「入/失」字串
        h_stats = f"{safe_val(row,11):.1f} / {safe_val(row,12):.1f}"
        a_stats = f"{safe_val(row,13):.1f} / {safe_val(row,14):.1f}"

        html += f"""<tr>
        <td style="color:#888; font-size:12px;">{v(0)}</td>
        <td><span class="league-tag">{v(1)}</span></td>
        <td style="text-align:left; font-weight:bold;">{v(2)}</td>
        <td style="text-align:left; font-weight:bold;">{v(3)}</td>
        <td><span class="rank-badge">{v(4)}</span> vs <span class="rank-badge">{v(5)}</span></td>
        <td class="col-goals">{h_stats}</td>
        <td class="col-goals">{a_stats}</td>
        <td class="{c_res}">{txt_res}</td>
        <td style="color:#888;">{exp_g:.2f}球</td>
        </tr>"""
        count += 1
        
    html += "</tbody></table></div>"
    st.markdown(html, unsafe_allow_html=True)
    st.caption(f"共顯示 {count} 場賽事 | 數據格式：平均入球 / 平均失球")

else:
    st.error("無法讀取數據，請稍後再試。")