import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import math

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI Render Safe (V16.0 Pro)", page_icon="⚽", layout="wide")

# ================= CSS 優化 (深色模式 + 視覺化分析) =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    
    /* 卡片主體 */
    .compact-card { 
        background-color: #1a1c24; 
        border: 1px solid #333; 
        border-radius: 10px; 
        padding: 12px; 
        margin-bottom: 12px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* 頂部資訊列 */
    .match-header { 
        display: flex; 
        justify-content: space-between; 
        color: #aaa; 
        font-size: 0.75rem; 
        margin-bottom: 8px; 
        border-bottom: 1px solid #333; 
        padding-bottom: 4px; 
    }
    
    /* 球隊行 (包含排名與身價) */
    .team-row { display: grid; grid-template-columns: 3fr 1fr 3fr; align-items: center; margin-bottom: 8px; }
    .team-info-box { display: flex; flex-direction: column; }
    .team-name { font-weight: bold; font-size: 1.1rem; color: #fff; }
    .team-meta { font-size: 0.7rem; color: #bbb; margin-top: 2px; }
    .rank-badge { background: #444; color: #fff; padding: 1px 4px; border-radius: 3px; font-size: 0.65rem; margin-right: 4px; }
    .value-tag { color: #ffd700; font-size: 0.65rem; }
    
    .team-score { font-size: 1.4rem; font-weight: bold; color: #00ffea; text-align: center; letter-spacing: 2px; }
    
    /* 戰力導向條 (Dominance Bar) - 新增功能 */
    .dom-bar-container { width: 100%; height: 6px; background: #333; border-radius: 3px; margin: 8px 0; position: relative; overflow: hidden; }
    .dom-bar-fill { height: 100%; transition: width 0.5s; }
    .dom-bar-label { display: flex; justify-content: space-between; font-size: 0.65rem; color: #888; margin-bottom: 2px; }
    
    /* 數據矩陣 */
    .grid-matrix { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; font-size: 0.75rem; margin-top: 8px; text-align: center; }
    .matrix-col { display: flex; flex-direction: column; gap: 3px; background: #222; padding: 4px; border-radius: 4px; border: 1px solid #333; }
    .matrix-header { color: #ff9800; font-weight: bold; font-size: 0.7rem; margin-bottom: 2px; text-transform: uppercase; }
    .matrix-cell { display: flex; justify-content: space-between; padding: 2px 4px; background: #2b2d35; border-radius: 3px; }
    
    /* 數值高亮 */
    .cell-label { color: #aaa; }
    .cell-val { color: #fff; font-weight: bold; }
    .cell-val-high { color: #00ff00; font-weight: bold; text-shadow: 0 0 2px #00ff00; }
    .cell-val-low { color: #ff4444; }
    
    /* 底部建議區 */
    .footer-box { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; background: #16181d; padding: 6px; border-radius: 6px; }
    .sugg-text { color: #00ff00; font-size: 0.8rem; font-weight: bold; }
    .risk-badge { padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; color: #fff; }
    .risk-low { background: #28a745; }
    .risk-med { background: #17a2b8; }
    .risk-high { background: #dc3545; }
    
    /* EV 標籤 */
    .ev-badge { background: linear-gradient(45deg, #FFD700, #FFA500); color: #000; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 0.7rem; margin-left: 5px; }
</style>
""", unsafe_allow_html=True)

# ================= 輔助函式 =================
def get_form_html(form_str):
    if pd.isna(form_str) or str(form_str) == 'N/A': return "-"
    html = ""
    for char in str(form_str).strip()[-5:]:
        color = "#28a745" if char.upper()=='W' else "#ffc107" if char.upper()=='D' else "#dc3545"
        html += f"<span style='color:{color}; font-weight:bold; margin-left:1px;'>{char}</span>"
    return html

def get_dominance_bar(dom_idx):
    """
    生成戰力導向條 HTML
    dom_idx > 0: 主隊強 (藍色)
    dom_idx < 0: 客隊強 (紅色)
    範圍通常在 -3 到 3 之間
    """
    try:
        val = float(dom_idx)
    except:
        val = 0
    
    # 正規化到 0-100% (假設最大偏差是 3.0)
    percentage = 50 + (val / 3.0 * 50)
    percentage = max(5, min(95, percentage)) # 限制在 5% - 95%
    
    color = "#00ccff" if val > 0 else "#ff4444"
    
    html = f"""
    <div class='dom-bar-label'>
        <span>{'⚔️ 主控' if val > 0.5 else ''}</span>
        <span style='color:{color}; font-weight:bold;'>{val:+.2f} 指數</span>
        <span>{'客控 ⚔️' if val < -0.5 else ''}</span>
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
        df = pd.DataFrame(data)
        return df
    except Exception as e: 
        st.error(f"連線錯誤: {e}")
        return None

# ================= 主程式 =================
def main():
    st.title("⚽ 足球AI Render Safe (V16.0 Pro)")
    
    df = load_data()
    if df is not None and not df.empty:
        if st.sidebar.button("🔄 刷新即時數據", use_container_width=True): 
            st.cache_data.clear()
            st.rerun()
    else:
        st.warning("⚠️ 無法讀取數據，請檢查 run_me.py 是否執行成功。")
        return

    # === 數據類型轉換 (防呆) ===
    # 這些欄位必須是數字
    numeric_cols = ['xG主','xG客','主勝率','和局率','客勝率','HT主','HT和','HT客',
                    'AH-0.5','AH-1.0','AH-2.0','C75','C85','C95',
                    '大球率1.5','大球率2.5','大球率3.5','主導指數',
                    '凱利主(%)','凱利客(%)']
    
    # 這些欄位是文字，不需要轉數字 (保留身價的 € 符號)
    text_cols = ['主隊身價', '客隊身價', '主排名', '客排名', '狀態', '聯賽', '時間']

    for col in numeric_cols: 
        if col in df.columns: 
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # === 側邊欄篩選 (Restored Features) ===
    st.sidebar.header("🔍 賽事篩選")
    
    # 1. 聯賽篩選
    leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
    sel_lg = st.sidebar.selectbox("🏆 選擇聯賽:", leagues)
    
    # 2. 狀態篩選 (New)
    statuses = ["全部", "未開賽", "進行中", "完場"]
    # 預設邏輯：如果數據裡有進行中的，優先顯示；否則顯示全部
    default_status = "全部"
    sel_status = st.sidebar.radio("⏱️ 比賽狀態:", statuses, index=0)
    
    # 3. 日期篩選
    df['日期'] = df['時間'].apply(lambda x: str(x).split(' ')[0])
    dates = ["全部"] + sorted(list(set(df['日期'])))
    sel_date = st.sidebar.selectbox("📅 選擇日期:", dates)

    # === 執行篩選 ===
    if sel_lg != "全部": df = df[df['聯賽'] == sel_lg]
    if sel_date != "全部": df = df[df['日期'] == sel_date]
    if sel_status != "全部": 
        if sel_status == "未開賽": df = df[df['狀態'] == '未開賽']
        elif sel_status == "進行中": df = df[df['狀態'].isin(['進行中', '中場休息'])]
        elif sel_status == "完場": df = df[df['狀態'] == '完場']

    # 排序：進行中 -> 未開賽 -> 完場
    status_order = {'進行中': 0, '中場休息': 0, '未開賽': 1, '完場': 2}
    df['status_sort'] = df['狀態'].map(status_order).fillna(3)
    df = df.sort_values(by=['status_sort', '時間'], ascending=True)

    st.write(f"共找到 {len(df)} 場賽事")

    # === 渲染卡片 ===
    for index, row in df.iterrows():
        time_part = str(row['時間']).split(' ')[1]
        
        # === 樣式邏輯 ===
        # 勝率高亮
        cls_h = "cell-val-high" if row['主勝率'] > 55 else "cell-val"
        cls_a = "cell-val-high" if row['客勝率'] > 55 else "cell-val"
        cls_o25 = "cell-val-high" if row['大球率2.5'] > 60 else "cell-val"
        
        # 凱利值 EV 判斷 (有價值投注)
        kelly_h = row.get('凱利主(%)', 0)
        kelly_a = row.get('凱利客(%)', 0)
        ev_tag = ""
        if kelly_h > 8: ev_tag = "<span class='ev-badge'>💰 主值</span>"
        elif kelly_a > 8: ev_tag = "<span class='ev-badge'>💰 客值</span>"
        
        # 身價與排名顯示 (Restored)
        h_rank = f"<span class='rank-badge'>#{row.get('主排名','-')}</span>"
        a_rank = f"<span class='rank-badge'>#{row.get('客排名','-')}</span>"
        h_val = f"<span class='value-tag'>{row.get('主隊身價','')}</span>"
        a_val = f"<span class='value-tag'>{row.get('客隊身價','')}</span>"

        # 風險顏色
        risk = row.get('風險評級', '穩健')
        risk_cls = "risk-high" if "險" in risk else "risk-low" if "穩" in risk else "risk-med"

        # 1. Card Start
        html = "<div class='compact-card'>"
        
        # 2. Header (時間 | 聯賽 | 狀態)
        html += f"<div class='match-header'><span>🕒 {time_part} | {row['聯賽']}</span><span style='color:#fff;'>{row['狀態']}</span></div>"
        
        # 3. Team Row (包含排名與身價)
        html += "<div class='team-row'>"
        # Home Team
        html += f"<div style='text-align:right;' class='team-info-box'>"
        html += f"  <div class='team-name'>{row['主隊']} {h_rank}</div>"
        html += f"  <div class='team-meta'>{h_val} | xG:{row['xG主']} {get_form_html(row.get('主近況'))}</div>"
        html += "</div>"
        
        # Score
        html += f"<div class='team-score'>{row['主分']} - {row['客分']}</div>"
        
        # Away Team
        html += f"<div style='text-align:left;' class='team-info-box'>"
        html += f"  <div class='team-name'>{a_rank} {row['客隊']}</div>"
        html += f"  <div class='team-meta'>{get_form_html(row.get('客近況'))} xG:{row['xG客']} | {a_val}</div>"
        html += "</div>"
        html += "</div>" # End Team Row
        
        # 4. Dominance Bar (新功能：戰力分析)
        html += get_dominance_bar(row.get('主導指數', 0))
        
        # 5. Grid Matrix
        html += "<div class='grid-matrix'>"
        
        # Col 1: Full Time Probs
        html += f"<div class='matrix-col'><div class='matrix-header'>全場勝率 {ev_tag}</div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>主</span><span class='{cls_h}'>{row['主勝率']}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>和</span><span class='cell-val'>{row['和局率']}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>客</span><span class='{cls_a}'>{row['客勝率']}%</span></div></div>"
        
        # Col 2: Asian Handicap
        html += "<div class='matrix-col'><div class='matrix-header'>亞盤概率</div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>-0.5</span><span class='cell-val'>{row['AH-0.5']}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>-1.0</span><span class='cell-val'>{row['AH-1.0']}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>-2.0</span><span class='cell-val'>{row['AH-2.0']}%</span></div></div>"
        
        # Col 3: Goals (OU)
        html += "<div class='matrix-col'><div class='matrix-header'>大小球</div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>1.5大</span><span class='cell-val'>{row['大球率1.5']}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>2.5大</span><span class='{cls_o25}'>{row['大球率2.5']}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>BTTS</span><span class='cell-val'>{row.get('BTTS',0)}%</span></div></div>"
        
        # Col 4: Corners
        html += "<div class='matrix-col'><div class='matrix-header'>角球數</div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>7.5+</span><span class='cell-val'>{row['C75']}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>8.5+</span><span class='cell-val'>{row['C85']}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>9.5+</span><span class='cell-val'>{row['C95']}%</span></div></div>"
        
        # Col 5: Half Time
        html += "<div class='matrix-col'><div class='matrix-header'>半場</div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>主</span><span class='cell-val'>{row['HT主']}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>和</span><span class='cell-val'>{row['HT和']}%</span></div>"
        html += f"<div class='matrix-cell'><span class='cell-label'>客</span><span class='cell-val'>{row['HT客']}%</span></div></div>"

        html += "</div>" # End Grid

        # 6. Suggestion Footer
        html += f"""
        <div class='footer-box'>
            <div style='display:flex; flex-direction:column;'>
                <span class='sugg-text'>🎯 {row.get('首選推介')}</span>
                <span style='font-size:0.7rem; color:#aaa;'>盤口: {row.get('亞盤建議')} | 角球: {row.get('角球預測')}</span>
            </div>
            <div style='text-align:right;'>
                 <span class='risk-badge {risk_cls}'>{risk}</span>
                 <div style='font-size:0.65rem; color:#888; margin-top:2px;'>{row.get('智能標籤','')}</div>
            </div>
        </div>
        """
        
        html += "</div>" # End Card
        st.markdown(html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
