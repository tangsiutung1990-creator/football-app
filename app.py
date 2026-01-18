import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI Pro (V27.0)", page_icon="⚽", layout="wide")

# ================= CSS 優化 =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    
    /* 強制縮窄側邊欄 (約縮小 1/3) */
    [data-testid="stSidebar"] {
        min-width: 200px !important;
        max-width: 250px !important;
    }
    
    .compact-card { background-color: #1a1c24; border: 1px solid #333; border-radius: 8px; padding: 10px; margin-bottom: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); font-family: 'Arial', sans-serif; }
    
    .match-header { display: flex; justify-content: space-between; color: #888; font-size: 0.8rem; margin-bottom: 8px; border-bottom: 1px solid #333; padding-bottom: 4px; }
    
    /* 比分置中佈局：左隊 | 比分 | 右隊 */
    .content-row { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; margin-bottom: 10px; gap: 10px; }
    
    .team-left { text-align: right; }
    .team-right { text-align: left; }
    .team-name { font-weight: bold; font-size: 1.2rem; color: #fff; margin-bottom: 2px; line-height: 1.2; } 
    .team-sub { font-size: 0.75rem; color: #aaa; }
    
    .score-area { 
        text-align: center; 
        font-size: 2.4rem; 
        font-weight: bold; 
        color: #00ffea; 
        letter-spacing: 2px; 
        line-height: 1; 
        padding: 0 15px;
        background: #222;
        border-radius: 6px;
    }
    
    /* 6欄緊湊網格 */
    .grid-matrix { display: grid; grid-template-columns: repeat(6, 1fr); gap: 2px; font-size: 0.75rem; margin-top: 8px; text-align: center; }
    .matrix-col { background: #222; padding: 2px; border-radius: 4px; border: 1px solid #333; display: flex; flex-direction: column; }
    .matrix-header { color: #ff9800; font-weight: bold; font-size: 0.75rem; margin-bottom: 2px; border-bottom: 1px solid #444; padding-bottom: 1px; }
    .matrix-cell { display: flex; justify-content: space-between; padding: 0 4px; align-items: center; line-height: 1.4; }
    .cell-label { color: #999; font-size: 0.75rem; }
    .cell-val { color: #fff; font-weight: bold; font-size: 0.9rem; }
    .cell-val-high { color: #00ff00; font-weight: bold; font-size: 0.9rem; }
    
    .footer-box { display: flex; justify-content: space-between; margin-top: 8px; background: #16181d; padding: 8px 10px; border-radius: 6px; align-items: center; border-left: 4px solid #00b09b; }
    .sugg-text { color: #fff; font-size: 1.1rem; font-weight: bold; }
    .conf-badge { background: #333; color: #00ffea; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.9rem; border: 1px solid #00ffea; }
</style>
""", unsafe_allow_html=True)

def clean_pct(val):
    if pd.isna(val) or val == '': return 0
    try:
        f = float(str(val).replace('%', ''))
        if f > 100: f = 100 
        return int(f)
    except: return 0

def format_odds(val):
    try:
        f = float(val)
        if f <= 1: return "-"
        return f"{f:.2f}"
    except: return "-"

def main():
    st.title("⚽ 足球AI Pro (V27.0 Ultimate)")
    
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
    
    if '聯賽' in df.columns:
        leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
        sel_lg = st.sidebar.selectbox("聯賽:", leagues)
        if sel_lg != "全部": df = df[df['聯賽'] == sel_lg]

    status_filter = st.sidebar.radio("狀態:", ["全部", "未開賽", "進行中", "完場", "延遲/取消"])
    if status_filter == "未開賽": df = df[df['狀態'] == '未開賽']
    elif status_filter == "進行中": df = df[df['狀態'] == '進行中']
    elif status_filter == "完場": df = df[df['狀態'] == '完場']
    elif status_filter == "延遲/取消": df = df[df['狀態'].str.contains('延遲|取消')]

    if '時間' in df.columns:
        df['日期'] = df['時間'].apply(lambda x: str(x).split(' ')[0])
        dates = ["全部"] + sorted(list(set(df['日期'])), reverse=True) 
        sel_date = st.sidebar.selectbox("日期:", dates)
        if sel_date != "全部": df = df[df['日期'] == sel_date]

    df['sort_idx'] = df['狀態'].apply(lambda x: 0 if x == '進行中' else 1 if x=='未開賽' else 2)
    df = df.sort_values(by=['sort_idx', '時間'])

    for index, row in df.iterrows():
        prob_h = clean_pct(row.get('主勝率', 0))
        prob_a = clean_pct(row.get('客勝率', 0))
        prob_o25 = clean_pct(row.get('大2.5', 0))
        
        cls_h = "cell-val-high" if prob_h > 50 else "cell-val"
        cls_a = "cell-val-high" if prob_a > 50 else "cell-val"
        cls_o25 = "cell-val-high" if prob_o25 > 55 else "cell-val"
        
        score_txt = f"{row.get('主分')} - {row.get('客分')}" if str(row.get('主分')) != '' else "VS"
        advice = row.get('推介', '暫無')
        confidence = row.get('信心', 0)

        card_html = ""
        card_html += f"<div class='compact-card'>"
        card_html += f"<div class='match-header'><span>{row.get('時間','')} | {row.get('聯賽','')}</span><span>{row.get('狀態','')}</span></div>"
        
        # 新佈局：置中比分
        card_html += f"<div class='content-row'>"
        card_html += f"<div class='team-left'>"
        card_html += f"<div class='team-name'>{row.get('主隊','')}</div>"
        card_html += f"<div class='team-sub'>狀態: {row.get('主狀態','-')}</div>"
        card_html += f"</div>"
        
        card_html += f"<div class='score-area'>{score_txt}</div>"
        
        card_html += f"<div class='team-right'>"
        card_html += f"<div class='team-name'>{row.get('客隊','')}</div>"
        card_html += f"<div class='team-sub'>狀態: {row.get('客狀態','-')}</div>"
        card_html += f"</div>"
        card_html += f"</div>"
        
        # Grid Matrix
        card_html += f"<div class='grid-matrix'>"
        
        # 1. 勝率
        card_html += f"<div class='matrix-col'><div class='matrix-header'>勝率</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>主</span><span class='{cls_h}'>{prob_h}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>和</span><span class='cell-val'>{clean_pct(row.get('和局率',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>客</span><span class='{cls_a}'>{prob_a}%</span></div></div>"
        
        # 2. 亞盤主
        card_html += f"<div class='matrix-col'><div class='matrix-header'>主亞盤%</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>平</span><span class='cell-val'>{clean_pct(row.get('主平',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+0.5</span><span class='cell-val'>{clean_pct(row.get('主+0.5',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+1</span><span class='cell-val'>{clean_pct(row.get('主+1',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>-2</span><span class='cell-val'>{clean_pct(row.get('主-2',0))}%</span></div></div>"
        
        # 3. 亞盤客
        card_html += f"<div class='matrix-col'><div class='matrix-header'>客亞盤%</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>平</span><span class='cell-val'>{clean_pct(row.get('客平',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+0.5</span><span class='cell-val'>{clean_pct(row.get('客+0.5',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+1</span><span class='cell-val'>{clean_pct(row.get('客+1',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>-2</span><span class='cell-val'>{clean_pct(row.get('客-2',0))}%</span></div></div>"
        
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
        card_html += f"<div class='matrix-cell'><span class='cell-label'>主賠</span><span style='color:#00e5ff;'>{format_odds(row.get('主賠'))}</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>客賠</span><span style='color:#00e5ff;'>{format_odds(row.get('客賠'))}</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>K主</span><span class='cell-val'>{clean_pct(row.get('凱利主',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>K客</span><span class='cell-val'>{clean_pct(row.get('凱利客',0))}%</span></div></div>"
        
        card_html += f"</div>" # End Grid
        
        # Footer
        card_html += f"<div class='footer-box'>"
        card_html += f"<span class='sugg-text'>🎯 {advice}</span>"
        card_html += f"<span class='conf-badge'>信心: {confidence}%</span>"
        card_html += f"</div>"
        card_html += f"</div>"

        st.markdown(card_html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
