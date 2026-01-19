import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI Pro (V36.0 Pro)", page_icon="⚽", layout="wide")

# ================= CSS 優化 =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    [data-testid="stSidebar"] { min-width: 200px !important; max-width: 250px !important; }
    
    .compact-card { background-color: #1a1c24; border: 1px solid #333; border-radius: 8px; padding: 10px; margin-bottom: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); font-family: 'Arial', sans-serif; }
    
    .match-header { display: flex; justify-content: space-between; color: #888; font-size: 0.8rem; margin-bottom: 8px; border-bottom: 1px solid #333; padding-bottom: 4px; }
    
    .content-row { display: grid; grid-template-columns: 7fr 3fr; align-items: center; margin-bottom: 10px; }
    .teams-area { text-align: left; display: flex; flex-direction: column; justify-content: center; }
    .team-name { font-weight: bold; font-size: 1.15rem; color: #fff; margin-bottom: 2px; display: flex; align-items: center; gap: 6px; } 
    
    .rank-badge { background: #444; color: #fff; font-size: 0.7rem; padding: 1px 4px; border-radius: 3px; font-weight: normal; }
    .rank-top { background: #ff9800; color: #000; }
    .rank-bot { background: #d32f2f; color: #fff; }
    
    .team-sub { font-size: 0.75rem; color: #aaa; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 2px;}
    .form-dots { display: flex; gap: 2px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
    .dot-W { background-color: #00e676; }
    .dot-D { background-color: #ffeb3b; }
    .dot-L { background-color: #ff5252; }
    .dot-N { background-color: #555; }
    
    .score-area { text-align: right; display: flex; flex-direction: column; align-items: flex-end; }
    .score-main { font-size: 2.0rem; font-weight: bold; color: #00ffea; letter-spacing: 2px; line-height: 1; }
    .xg-sub { font-size: 0.7rem; color: #888; margin-top: 4px; border: 1px solid #444; padding: 1px 4px; border-radius: 4px; }
    
    .inj-badge { color: #ff4b4b; font-weight: bold; font-size: 0.75rem; border: 1px solid #ff4b4b; padding: 0 4px; border-radius: 3px; }
    .h2h-badge { color: #ffd700; font-weight: bold; font-size: 0.75rem; background: #333; padding: 0 4px; border-radius: 3px; }
    .val-badge { color: #000; background: #ffd700; font-weight: bold; font-size: 0.75rem; padding: 0 4px; border-radius: 3px; margin-left: 5px; }

    .grid-matrix { display: grid; grid-template-columns: repeat(6, 1fr); gap: 2px; font-size: 0.75rem; margin-top: 8px; text-align: center; }
    .matrix-col { background: #222; padding: 2px; border-radius: 4px; border: 1px solid #333; display: flex; flex-direction: column; }
    .matrix-header { color: #ff9800; font-weight: bold; font-size: 0.75rem; margin-bottom: 2px; border-bottom: 1px solid #444; padding-bottom: 1px; white-space: nowrap; overflow: hidden; }
    .matrix-cell { display: flex; justify-content: space-between; padding: 0 4px; align-items: center; line-height: 1.4; }
    .cell-label { color: #999; font-size: 0.75rem; }
    .cell-val { color: #fff; font-weight: bold; font-size: 0.9rem; }
    .cell-val-high { color: #00ff00; font-weight: bold; font-size: 0.9rem; }
    .cell-val-zero { color: #444; font-size: 0.9rem; }
    
    .footer-box { display: flex; justify-content: space-between; margin-top: 8px; background: #16181d; padding: 8px 10px; border-radius: 6px; align-items: center; border-left: 4px solid #00b09b; }
    .sugg-text { color: #fff; font-size: 1.1rem; font-weight: bold; }
    .conf-badge { background: #333; color: #00ffea; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.9rem; border: 1px solid #00ffea; }
    .source-tag { font-size: 0.6rem; color: #555; margin-left: 10px; }
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

def fmt_pct_display(val, threshold=50, is_o25=False):
    v = clean_pct(val)
    if v == 0: return "<span class='cell-val-zero'>-</span>"
    css_class = "cell-val-high" if (v > threshold) else "cell-val"
    if is_o25 and v > 55: css_class = "cell-val-high"
    return f"<span class='{css_class}'>{v}%</span>"

def render_form_dots(form_str):
    if not form_str or form_str == 'N/A': return ""
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
    try:
        r = int(rank)
        cls = "rank-badge"
        if r <= 4: cls += " rank-top"
        if r >= 18: cls += " rank-bot"
        return f"<span class='{cls}'>#{r}</span>"
    except: return ""

def main():
    st.title("⚽ 足球AI Pro (V36.0 Pro Splits)")
    
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

    st.sidebar.header("🔍 篩選")
    if '聯賽' in df.columns:
        leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
        sel_lg = st.sidebar.selectbox("聯賽:", leagues)
        if sel_lg != "全部": df = df[df['聯賽'] == sel_lg]

    status_filter = st.sidebar.radio("狀態:", ["全部", "未開賽", "進行中", "完場"])
    if status_filter == "未開賽": df = df[df['狀態'] == '未開賽']
    elif status_filter == "進行中": df = df[df['狀態'] == '進行中']
    elif status_filter == "完場": df = df[df['狀態'] == '完場']

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
        
        score_txt = f"{row.get('主分')} - {row.get('客分')}" if str(row.get('主分')) != '' else "VS"
        advice = row.get('推介', '暫無')
        confidence = row.get('信心', 0)
        source = row.get('數據源', 'API')
        
        inj_h = clean_pct(row.get('主傷', 0))
        inj_a = clean_pct(row.get('客傷', 0))
        inj_h_tag = f"<span class='inj-badge'>🚑 {inj_h}</span>" if inj_h > 0 else ""
        inj_a_tag = f"<span class='inj-badge'>🚑 {inj_a}</span>" if inj_a > 0 else ""
        
        h2h_h = row.get('H2H主', 0); h2h_d = row.get('H2H和', 0); h2h_a = row.get('H2H客', 0)
        h2h_tag = f"<span class='h2h-badge'>⚔️ {h2h_h}-{h2h_d}-{h2h_a}</span>"
        
        rank_h = render_rank_badge(row.get('主排名', ''))
        rank_a = render_rank_badge(row.get('客排名', ''))
        form_h_dots = render_form_dots(row.get('主走勢', ''))
        form_a_dots = render_form_dots(row.get('客走勢', ''))
        
        val_h_tag = f"<span class='val-badge'>💰 VALUE</span>" if row.get('主Value') == '💰' else ""
        val_a_tag = f"<span class='val-badge'>💰 VALUE</span>" if row.get('客Value') == '💰' else ""
        
        xg_txt = f"xG: {row.get('xG主',0)} - {row.get('xG客',0)}"

        card_html = f"<div class='compact-card'>"
        card_html += f"<div class='match-header'><span>{row.get('時間','')} | {row.get('聯賽','')}</span><span>{row.get('狀態','')}</span></div>"
        
        card_html += f"<div class='content-row'>"
        card_html += f"<div class='teams-area'>"
        card_html += f"<div class='team-name'>{row.get('主隊','')} {rank_h} {inj_h_tag} {val_h_tag}</div>"
        card_html += f"<div class='team-sub'>{form_h_dots} {h2h_tag}</div>"
        card_html += f"<div class='team-name' style='margin-top:6px;'>{row.get('客隊','')} {rank_a} {inj_a_tag} {val_a_tag}</div>"
        card_html += f"<div class='team-sub'>{form_a_dots}</div>"
        card_html += f"</div>"
        
        card_html += f"<div class='score-area'>"
        card_html += f"<span class='score-main'>{score_txt}</span>"
        card_html += f"<span class='xg-sub'>{xg_txt}</span>"
        card_html += f"</div>"
        card_html += f"</div>"
        
        # Grid Matrix
        card_html += f"<div class='grid-matrix'>"
        
        card_html += f"<div class='matrix-col'><div class='matrix-header'>API 勝率</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>主</span>{fmt_pct_display(prob_h)}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>和</span><span class='cell-val'>{clean_pct(row.get('和局率',0))}%</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>客</span>{fmt_pct_display(prob_a)}</div></div>"
        
        card_html += f"<div class='matrix-col'><div class='matrix-header'>主亞盤%</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>平</span>{fmt_pct_display(row.get('主平',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>0/-0.5</span>{fmt_pct_display(row.get('主0/-0.5',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>-0.5/-1</span>{fmt_pct_display(row.get('主-0.5/-1',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>-1/-1.5</span>{fmt_pct_display(row.get('主-1/-1.5',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>0/+0.5</span>{fmt_pct_display(row.get('主0/+0.5',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+0.5/+1</span>{fmt_pct_display(row.get('主+0.5/+1',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+1/+1.5</span>{fmt_pct_display(row.get('主+1/+1.5',0))}</div></div>"
        
        card_html += f"<div class='matrix-col'><div class='matrix-header'>客亞盤%</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>平</span>{fmt_pct_display(row.get('客平',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>0/-0.5</span>{fmt_pct_display(row.get('客0/-0.5',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>-0.5/-1</span>{fmt_pct_display(row.get('客-0.5/-1',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>-1/-1.5</span>{fmt_pct_display(row.get('客-1/-1.5',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>0/+0.5</span>{fmt_pct_display(row.get('客0/+0.5',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+0.5/+1</span>{fmt_pct_display(row.get('客+0.5/+1',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>+1/+1.5</span>{fmt_pct_display(row.get('客+1/+1.5',0))}</div></div>"
        
        card_html += f"<div class='matrix-col'><div class='matrix-header'>全場/進球</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>FTS主</span>{fmt_pct_display(row.get('FTS主',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>FTS客</span>{fmt_pct_display(row.get('FTS客',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>BTTS</span>{fmt_pct_display(row.get('BTTS',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>大0.5</span>{fmt_pct_display(row.get('大0.5',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>大1.5</span>{fmt_pct_display(row.get('大1.5',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>大2.5</span>{fmt_pct_display(prob_o25, 55, True)}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>大3.5</span>{fmt_pct_display(row.get('大3.5',0))}</div></div>"
        
        card_html += f"<div class='matrix-col'><div class='matrix-header'>半場大小</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>H0.5</span>{fmt_pct_display(row.get('HT0.5',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>H1.5</span>{fmt_pct_display(row.get('HT1.5',0))}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>H2.5</span>{fmt_pct_display(row.get('HT2.5',0))}</div></div>"
        
        card_html += f"<div class='matrix-col'><div class='matrix-header'>賠率/凱利</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>主賠</span><span style='color:#00e5ff;'>{format_odds(row.get('主賠'))}</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>客賠</span><span style='color:#00e5ff;'>{format_odds(row.get('客賠'))}</span></div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>K主</span>{fmt_pct_display(row.get('凱利主',0), 0)}</div>"
        card_html += f"<div class='matrix-cell'><span class='cell-label'>K客</span>{fmt_pct_display(row.get('凱利客',0), 0)}</div></div>"
        
        card_html += f"</div>"
        
        card_html += f"<div class='footer-box'>"
        card_html += f"<span class='sugg-text'>🎯 {advice}</span>"
        card_html += f"<span class='conf-badge'>信心: {confidence}% <span class='source-tag'>({source})</span></span>"
        card_html += f"</div>"
        card_html += f"</div>"

        st.markdown(card_html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
