import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import math

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI Render Safe (V22.0 Pro)", page_icon="⚽", layout="wide")

# ================= CSS 優化 (6欄佈局 + 緊湊設計) =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    
    /* 卡片主體 */
    .compact-card { 
        background-color: #1a1c24; 
        border: 1px solid #333; 
        border-radius: 12px; 
        padding: 12px; 
        margin-bottom: 12px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        font-size: 1rem; 
    }
    
    .match-header { 
        display: flex; 
        justify-content: space-between; 
        color: #bbb; 
        font-size: 0.85rem; 
        margin-bottom: 8px; 
        border-bottom: 1px solid #333; 
        padding-bottom: 4px; 
    }
    
    /* 球隊行 */
    .team-row { display: grid; grid-template-columns: 3fr 1fr 3fr; align-items: center; margin-bottom: 10px; }
    .team-name { font-weight: bold; font-size: 1.25rem; color: #fff; } 
    .team-meta { font-size: 0.8rem; color: #ccc; margin-top: 4px; }
    .rank-badge { background: #444; color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin-right: 5px; }
    .value-tag { color: #ffd700; font-size: 0.75rem; font-weight: bold; }
    .team-score { font-size: 1.8rem; font-weight: bold; color: #00ffea; text-align: center; letter-spacing: 2px; }
    
    /* 戰力導向條 */
    .dom-bar-container { width: 100%; height: 8px; background: #333; border-radius: 4px; margin: 8px 0; position: relative; overflow: hidden; }
    .dom-bar-fill { height: 100%; transition: width 0.5s; }
    .dom-bar-label { display: flex; justify-content: space-between; font-size: 0.75rem; color: #999; margin-bottom: 2px; }
    
    /* 數據矩陣 - 6欄緊湊佈局 */
    /* 分配邏輯: 勝率(窄) | 亞盤主(中) | 亞盤客(中) | 大小(中) | 角球(窄) | 半場(窄) */
    .grid-matrix { 
        display: grid; 
        grid-template-columns: 0.8fr 1.2fr 1.2fr 1.2fr 0.8fr 0.8fr; 
        gap: 4px; 
        font-size: 0.8rem; 
        margin-top: 8px; 
        text-align: center; 
    }
    
    .matrix-col { display: flex; flex-direction: column; gap: 3px; background: #222; padding: 4px; border-radius: 6px; border: 1px solid #333; }
    /* 標題字體稍微縮小以適應窄欄 */
    .matrix-header { color: #ff9800; font-weight: bold; font-size: 0.7rem; margin-bottom: 3px; text-transform: uppercase; border-bottom: 1px dashed #444; padding-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    
    .matrix-cell { display: flex; justify-content: space-between; padding: 2px 4px; background: #2b2d35; border-radius: 4px; margin-bottom: 1px; align-items: center;}
    
    /* 數值樣式 */
    .cell-label { color: #aaa; font-weight: 500; font-size: 0.75rem; }
    .cell-val { color: #fff; font-weight: bold; font-size: 0.8rem; }
    .cell-val-high { color: #00ff00; font-weight: bold; text-shadow: 0 0 5px rgba(0,255,0,0.3); font-size: 0.8rem; }
    
    /* 底部資訊 */
    .footer-box { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; background: #16181d; padding: 6px; border-radius: 6px; }
    .sugg-text { color: #00ff00; font-size: 0.9rem; font-weight: bold; }
    .risk-badge { padding: 3px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: bold; color: #fff; }
    .risk-low { background: #28a745; }
    .risk-med { background: #17a2b8; }
    .risk-high { background: #dc3545; }
    .ev-badge { background: linear-gradient(45deg, #FFD700, #FFA500); color: #000; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 0.7rem; margin-left: 5px; }

</style>
""", unsafe_allow_html=True)

# ================= 內建運算核心 =================
def poisson_prob(k, lam):
    return (math.pow(lam, k) * math.exp(-lam)) / math.factorial(k)

def calculate_derived_stats(row):
    """
    即時運算補足數據 (含半場大小、主客亞盤)
    """
    try:
        xg_h = float(row.get('xG主', 1.3))
        xg_a = float(row.get('xG客', 1.0))
        h_win = float(row.get('主勝率', 33)) / 100
        a_win = float(row.get('客勝率', 33)) / 100
        draw = float(row.get('和局率', 33)) / 100
        
        # 半場 xG 估算
        ht_xg_h = xg_h * 0.45
        ht_xg_a = xg_a * 0.45
        total_ht_xg = ht_xg_h + ht_xg_a
        
        # Poisson for HT Goals
        p_0 = poisson_prob(0, total_ht_xg)
        p_1 = poisson_prob(1, total_ht_xg)
        p_2 = poisson_prob(2, total_ht_xg)
        
        prob_ht_o05 = (1 - p_0) * 100
        prob_ht_o15 = (1 - (p_0 + p_1)) * 100
        prob_ht_o25 = (1 - (p_0 + p_1 + p_2)) * 100
        
        # === 亞盤(主) 運算 ===
        # 平手盤 (主)
        level_h = h_win / (h_win + a_win + 0.0001) * 100
        # +0.5 (主) = 主勝 + 和
        plus_05_h = (h_win + draw) * 100
        # +1.0 (主) 近似
        plus_1_h = min(100, plus_05_h + 15)

        # === 亞盤(客) 運算 ===
        # 平手盤 (客)
        level_a = a_win / (h_win + a_win + 0.0001) * 100
        # -0.5 (客) = 客勝率
        minus_05_a = a_win * 100
        # +0.5 (客) = 客勝 + 和 (即主不勝)
        plus_05_a = (a_win + draw) * 100
        # -1.0 (客) 近似 (客勝 - 險勝) -> 估算為客勝的 55%
        minus_1_a = a_win * 0.55 * 100 
        # +1.0 (客) 近似
        plus_1_a = min(100, plus_05_a + 15)
        
        return {
            'ht_o05': prob_ht_o05,
            'ht_o15': prob_ht_o15,
            'ht_o25': prob_ht_o25,
            
            # 主盤
            'ah_level_h': level_h,
            'ah_plus_05_h': plus_05_h,
            'ah_plus_1_h': plus_1_h,
            
            # 客盤
            'ah_level_a': level_a,
            'ah_minus_05_a': minus_05_a,
            'ah_plus_05_a': plus_05_a,
            'ah_minus_1_a': minus_1_a,
            'ah_plus_1_a': plus_1_a
        }
    except:
        return {k:0 for k in ['ht_o05','ht_o15','ht_o25','ah_level_h','ah_plus_05_h','ah_plus_1_h','ah_level_a','ah_minus_05_a','ah_plus_05_a','ah_minus_1_a','ah_plus_1_a']}

# ================= 輔助顯示函式 =================
def fmt_pct(val):
    try:
        v = float(val)
        if v > 100: v = v / 100  
        if v > 100: v = v / 10
        return f"{v:.1f}"
    except: return "0.0"

def get_form_html(form_str):
    if pd.isna(form_str) or str(form_str) == 'N/A': return "-"
    html = ""
    for char in str(form_str).strip()[-5:]:
        color = "#28a745" if char.upper()=='W' else "#ffc107" if char.upper()=='D' else "#dc3545"
        html += f"<span style='color:{color}; font-weight:bold; margin-left:2px;'>{char}</span>"
    return html

def get_dominance_bar(dom_idx):
    try: val = float(dom_idx)
    except: val = 0
    percentage = 50 + (val / 3.0 * 50)
    percentage = max(5, min(95, percentage))
    color = "#00ccff" if val > 0 else "#ff4444"
    
    html = f"""
    <div class='dom-bar-label'>
        <span>{'⚔️ 主強' if val > 0.5 else ''}</span>
        <span style='color:{color}; font-weight:bold;'>{val:+.2f} 戰力指數</span>
        <span>{'客強 ⚔️' if val < -0.5 else ''}</span>
    </div>
    <div class='dom-bar-container'>
        <div class='dom-bar-fill' style='width: {percentage}%; background: linear-gradient(90deg, #ff4444, #00ccff);'>
            <div style='width: 2px; height: 100%; background: #fff; float: right;'></div>
        </div>
        <div style='position:absolute; left:50%; top:0; width:1px; height:100%; background:#555;'></div>
    </div>
    """
    return html

# ================= 連接 Google Sheet =================
@st.cache_data(ttl=60) 
def load_data():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if os.path.exists("key.json"): creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        else: creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e: return None

# ================= 主程式 =================
def main():
    st.title("⚽ 足球AI Render Safe (V16.3 Pro)")
    
    df = load_data()
    if df is not None and not df.empty:
        if st.sidebar.button("🔄 刷新數據", use_container_width=True): 
            st.cache_data.clear()
            st.rerun()
    else:
        st.warning("⚠️ 無法讀取數據。")
        return

    # 加入 '大球率3.5' 到檢查列表
    req_cols = ['xG主','xG客','主勝率','和局率','客勝率','HT主','HT和','HT客',
                'AH-0.5','AH-1.0','AH-2.0','C75','C85','C95',
                '大球率1.5','大球率2.5','大球率3.5','主導指數']
    for col in req_cols: 
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # === 側邊欄篩選 ===
    st.sidebar.header("🔍 篩選")
    leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
    sel_lg = st.sidebar.selectbox("聯賽:", leagues)
    status_filter = st.sidebar.radio("狀態:", ["全部", "未開賽", "進行中", "完場"])
    df['日期'] = df['時間'].apply(lambda x: str(x).split(' ')[0])
    dates = ["全部"] + sorted(list(set(df['日期'])))
    sel_date = st.sidebar.selectbox("日期:", dates)

    if sel_lg != "全部": df = df[df['聯賽'] == sel_lg]
    if sel_date != "全部": df = df[df['日期'] == sel_date]
    if status_filter == "未開賽": df = df[df['狀態'] == '未開賽']
    elif status_filter == "進行中": df = df[df['狀態'].isin(['進行中','中場休息'])]
    elif status_filter == "完場": df = df[df['狀態'] == '完場']
    
    df['sort_idx'] = df['狀態'].apply(lambda x: 0 if x in ['進行中','中場休息'] else 1 if x=='未開賽' else 2)
    df = df.sort_values(by=['sort_idx', '時間'])

    st.write(f"共找到 {len(df)} 場賽事")

    # === 渲染卡片 ===
    for index, row in df.iterrows():
        derived = calculate_derived_stats(row)
        time_part = str(row['時間']).split(' ')[1]
        
        # 樣式
        h_prob = float(row['主勝率']); a_prob = float(row['客勝率']); o25_prob = float(row['大球率2.5'])
        cls_h = "cell-val-high" if h_prob > 50 else "cell-val"
        cls_a = "cell-val-high" if a_prob > 50 else "cell-val"
        cls_o25 = "cell-val-high" if o25_prob > 55 else "cell-val"
        
        kelly_h = pd.to_numeric(row.get('凱利主(%)', 0), errors='coerce')
        ev_tag = "<span class='ev-badge'>💰EV</span>" if kelly_h > 10 else ""

        html = "<div class='compact-card'>"
        html += f"<div class='match-header'><span>{time_part} | {row['聯賽']}</span><span>{row['狀態']}</span></div>"
        
        html += "<div class='team-row'>"
        html += f"<div style='text-align:right;'><div class='team-name'>{row['主隊']} <span class='rank-badge'>#{row.get('主排名','-')}</span></div><div class='team-meta'><span class='value-tag'>{row.get('主隊身價','')}</span> | xG:{row['xG主']} {get_form_html(row.get('主近況'))}</div></div>"
        html += f"<div class='team-score'>{row['主分']} - {row['客分']}</div>"
        html += f"<div><div class='team-name'><span class='rank-badge'>#{row.get('客排名','-')}</span> {row['客隊']}</div><div class='team-meta'>{get_form_html(row.get('客近況'))} xG:{row['xG客']} | <span class='value-tag'>{row.get('客隊身價','')}</span></div></div>"
        html += "</div>"
        
        html += get_dominance_bar(row.get('主導指數', 0))
        
        # Matrix (6 Cols: 勝率 | 亞盤主 | 亞盤客 | 大小 | 角球 | 半場)
        html += "<div class='grid-matrix'>"
        
        # 1. 勝率
        html += f"<div class='matrix-col'><div class='matrix-header'>勝率 {ev_tag}</div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>主</span><span class='{cls_h}'>{fmt_pct(row['主勝率'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>和</span><span class='cell-val'>{fmt_pct(row['和局率'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>客</span><span class='{cls_a}'>{fmt_pct(row['客勝率'])}%</span></div></div>"
        
        # 2. 亞盤 (主)
        html += "<div class='matrix-col'><div class='matrix-header'>亞盤 (主)</div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>平(0)</span><span class='cell-val'>{fmt_pct(derived['ah_level_h'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>-0.5</span><span class='cell-val'>{fmt_pct(row['AH-0.5'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>+0.5</span><span class='cell-val'>{fmt_pct(derived['ah_plus_05_h'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>-1.0</span><span class='cell-val'>{fmt_pct(row['AH-1.0'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>+1.0</span><span class='cell-val'>{fmt_pct(derived['ah_plus_1_h'])}%</span></div></div>"
        
        # 3. 亞盤 (客)
        html += "<div class='matrix-col'><div class='matrix-header'>亞盤 (客)</div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>平(0)</span><span class='cell-val'>{fmt_pct(derived['ah_level_a'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>-0.5</span><span class='cell-val'>{fmt_pct(derived['ah_minus_05_a'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>+0.5</span><span class='cell-val'>{fmt_pct(derived['ah_plus_05_a'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>-1.0</span><span class='cell-val'>{fmt_pct(derived['ah_minus_1_a'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>+1.0</span><span class='cell-val'>{fmt_pct(derived['ah_plus_1_a'])}%</span></div></div>"
        
        # 4. 大小球 (新增 3.5大)
        html += "<div class='matrix-col'><div class='matrix-header'>大小球</div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>3.5大</span><span class='cell-val'>{fmt_pct(row['大球率3.5'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>2.5大</span><span class='{cls_o25}'>{fmt_pct(row['大球率2.5'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>1.5大</span><span class='cell-val'>{fmt_pct(row['大球率1.5'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label' style='color:#00ccff;'>H 0.5</span><span class='cell-val'>{fmt_pct(derived['ht_o05'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label' style='color:#00ccff;'>H 1.5</span><span class='cell-val'>{fmt_pct(derived['ht_o15'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>BTTS</span><span class='cell-val'>{fmt_pct(row.get('BTTS',0))}%</span></div></div>"
        
        # 5. 角球
        html += "<div class='matrix-col'><div class='matrix-header'>角球</div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>7.5+</span><span class='cell-val'>{fmt_pct(row['C75'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>8.5+</span><span class='cell-val'>{fmt_pct(row['C85'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>9.5+</span><span class='cell-val'>{fmt_pct(row['C95'])}%</span></div></div>"

        # 6. 半場勝率
        html += "<div class='matrix-col'><div class='matrix-header'>半場勝率</div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>主</span><span class='cell-val'>{fmt_pct(row['HT主'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>和</span><span class='cell-val'>{fmt_pct(row['HT和'])}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>客</span><span class='cell-val'>{fmt_pct(row['HT客'])}%</span></div></div>"
        
        html += "</div>" # End Grid
        
        # Footer
        risk_level = row.get('風險評級', '中')
        risk_cls = "risk-high" if "險" in risk_level else "risk-low" if "穩" in risk_level else "risk-med"
        
        html += f"""
        <div class='footer-box'>
            <div style='display:flex; flex-direction:column;'>
                <span class='sugg-text'>🎯 {row.get('首選推介')}</span>
                <span style='font-size:0.8rem; color:#aaa; margin-top:2px;'>建議: {row.get('亞盤建議')} | 預角: {row.get('角球預測')}</span>
            </div>
            <div style='text-align:right;'>
                 <span class='risk-badge {risk_cls}'>{risk_level}</span>
                 <div style='font-size:0.75rem; color:#888; margin-top:2px;'>{row.get('智能標籤','')}</div>
            </div>
        </div>
        """
        
        html += "</div>"
        st.markdown(html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
