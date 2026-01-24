import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from datetime import datetime, timedelta
import pytz
import json

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 
CSV_FILENAME = "football_data_backup.csv" 

st.set_page_config(page_title="足球AI Pro", page_icon="⚽", layout="wide")

# ================= CSS 極致優化 =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    div[data-testid="stPills"] { gap: 4px; }
    
    .compact-card { 
        background-color: #1a1c24; 
        border: 1px solid #333; 
        border-radius: 6px; 
        padding: 2px 4px; 
        margin-bottom: 6px; 
        font-family: 'Arial', sans-serif; 
    }
    
    .match-header { 
        display: flex; 
        justify-content: space-between; 
        color: #999; 
        font-size: 0.8rem; 
        margin-bottom: 2px; 
        border-bottom: 1px solid #333; 
        padding-bottom: 2px;
    }
    
    .content-row { 
        display: grid; 
        grid-template-columns: 6.5fr 3.5fr; 
        align-items: center; 
        margin-bottom: 2px; 
    }
    
    .team-name { 
        font-weight: bold; 
        font-size: 1.1rem; 
        color: #fff; 
        line-height: 1.1;
    } 
    
    .team-sub { 
        font-size: 0.75rem; 
        color: #bbb; 
        margin-top: 1px;
    }
    
    .score-main { font-size: 1.8rem; font-weight: bold; color: #00ffea; line-height: 1; text-align: right; }
    .score-sub { font-size: 0.75rem; color: #888; text-align: right; }

    /* 矩陣優化: 使用百分比寬度以達到最窄效果 */
    .grid-matrix { 
        display: grid; 
        grid-template-columns: 27% 23% 23% 27%; 
        gap: 1px; 
        margin-top: 2px; 
        background: #333; /* 邊框顏色 */
        border-radius: 4px;
        overflow: hidden;
    }
    
    .matrix-col { 
        padding: 1px 2px; 
        background: #222; /* 單元格背景 */
    }
    
    .matrix-header { 
        color: #ff9800; 
        font-size: 0.75rem; 
        font-weight: bold;
        text-align: center;
        border-bottom: 1px solid #444; 
        margin-bottom: 1px;
    }
    
    .matrix-cell { 
        display: flex; 
        justify-content: space-between; 
        padding: 0 1px; 
        color: #ddd; 
        font-size: 0.8rem; 
        line-height: 1.3;
    }
    
    .matrix-label { color: #888; font-size: 0.75rem; margin-right: 2px; }
    
    .cell-high { color: #00ff00; font-weight: bold; }
    .cell-mid { color: #ffff00; }
    
    .status-live { color: #ff4b4b; font-weight: bold; }
    .status-ft { color: #00ffea; }
    
    section[data-testid="stSidebar"] { width: 220px !important; }
</style>
""", unsafe_allow_html=True)

# ================= 輔助函數 =================
def clean_pct(val):
    try: return int(float(str(val).replace('%', '')))
    except: return 0

def fmt_pct(val, threshold=50):
    v = clean_pct(val)
    if v == 0: return "-"
    color_cls = 'cell-high' if v >= threshold else ('cell-mid' if v >= threshold - 10 else '')
    return f"<span class='{color_cls}'>{v}%</span>"

# ================= 核心修復函數 (關鍵修改) =================
def fix_private_key(key_str):
    """
    修復 private_key 中的換行符問題
    將 literal 的 string '\\n' 替換為真正的換行符 '\n'
    """
    if not key_str: return key_str
    return key_str.replace('\\n', '\n').strip()

def load_data():
    df = pd.DataFrame()
    source = "無"
    error_msg = ""
    
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = None

    try:
        # 1. 嘗試從環境變量 (優先 - 通常用於 GitHub Actions / Docker)
        json_text = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
        if json_text:
            try:
                creds_dict = json.loads(json_text)
                # ✅ 修復重點：強制處理 private_key
                if 'private_key' in creds_dict:
                    creds_dict['private_key'] = fix_private_key(creds_dict['private_key'])
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            except Exception as e:
                error_msg += f"Env Var Error: {str(e)}; "
        
        # 2. 嘗試從 Streamlit Secrets (通常用於 Streamlit Cloud)
        if not creds:
            try:
                if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
                    # ✅ 必須先轉換為標準 dict 才能修改 (Streamlit secrets 是唯讀的 AttrDict)
                    creds_dict = dict(st.secrets["gcp_service_account"])
                    
                    # ✅ 修復重點：強制處理 private_key
                    if 'private_key' in creds_dict:
                        creds_dict['private_key'] = fix_private_key(creds_dict['private_key'])
                    
                    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            except Exception as e:
                error_msg += f"Secrets Error: {str(e)}; "
            
        # 3. 嘗試從本地文件
        if not creds and os.path.exists("key.json"):
            try:
                creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
            except Exception as e:
                error_msg += f"Key File Error: {str(e)}; "
            
        if creds:
            client = gspread.authorize(creds)
            sheet = client.open(GOOGLE_SHEET_NAME).sheet1
            df = pd.DataFrame(sheet.get_all_records())
            source = "Cloud"
            
    except Exception as e:
        error_msg += f"Global Error: {str(e)}"
        pass

    if df.empty and os.path.exists(CSV_FILENAME):
        try:
            df = pd.read_csv(CSV_FILENAME)
            source = "Local"
        except Exception as e:
            error_msg += f"CSV Error: {str(e)}"
    
    return df, source, error_msg

# ================= 卡片渲染 =================
def render_match_card(row):
    prob_h = clean_pct(row.get('主勝率', 0))
    prob_d = clean_pct(row.get('和率', 0))
    prob_a = clean_pct(row.get('客勝率', 0))
    
    score_txt = f"{row.get('主分')} - {row.get('客分')}" if str(row.get('主分')) not in ['','nan'] else "VS"
    xg_txt = f"xG: {row.get('xG主',0)} - {row.get('xG客',0)}"
    status = row.get('狀態')
    status_cls = "status-live" if status == '進行中' else ("status-ft" if status == '完場' else "")
    
    ah_h_pick = row.get('亞盤主', '-')
    ah_h_prob = row.get('亞盤主率', 0)
    ah_a_pick = row.get('亞盤客', '-')
    ah_a_prob = row.get('亞盤客率', 0)
    
    card_html = f"""
    <div class='compact-card'>
        <div class='match-header'>
            <span>{row.get('時間')} | {row.get('聯賽')}</span>
            <span class='{status_cls}'>{status}</span>
        </div>
        <div class='content-row'>
            <div class='teams-area'>
                <div class='team-name'>{row.get('主隊')} <small style='color:#666; font-size:0.8rem'>#{row.get('主排名')}</small></div>
                <div class='team-name'>{row.get('客隊')} <small style='color:#666; font-size:0.8rem'>#{row.get('客排名')}</small></div>
                <div class='team-sub'>H2H: {row.get('H2H主')}-{row.get('H2H和')}-{row.get('H2H客')}</div>
            </div>
            <div class='score-area'>
                <div class='score-main'>{score_txt}</div>
                <div class='score-sub'>{xg_txt}</div>
            </div>
        </div>
        <div class='grid-matrix'>
            <div class='matrix-col'>
                <div class='matrix-header'>1x2</div>
                <div class='matrix-cell'><span class='matrix-label'>主</span>{fmt_pct(prob_h)} {row.get('主Value','')}</div>
                <div class='matrix-cell'><span class='matrix-label'>和</span>{fmt_pct(prob_d)} {row.get('和Value','')}</div>
                <div class='matrix-cell'><span class='matrix-label'>客</span>{fmt_pct(prob_a)} {row.get('客Value','')}</div>
            </div>
            <div class='matrix-col'>
                <div class='matrix-header'>全場</div>
                <div class='matrix-cell'><span class='matrix-label'>>1.5</span>{fmt_pct(row.get('大1.5'), 75)}</div>
                <div class='matrix-cell'><span class='matrix-label'>>2.5</span>{fmt_pct(row.get('大2.5'), 55)}</div>
                <div class='matrix-cell'><span class='matrix-label'>>3.5</span>{fmt_pct(row.get('大3.5'), 40)}</div>
            </div>
            <div class='matrix-col'>
                <div class='matrix-header'>半/雙</div>
                <div class='matrix-cell'><span class='matrix-label'>半>0.5</span>{fmt_pct(row.get('半大0.5'), 65)}</div>
                <div class='matrix-cell'><span class='matrix-label'>半>1.5</span>{fmt_pct(row.get('半大1.5'), 35)}</div>
                <div class='matrix-cell'><span class='matrix-label'>雙進</span>{fmt_pct(row.get('BTTS'), 55)}</div>
            </div>
            <div class='matrix-col'>
                <div class='matrix-header'>亞盤(%)</div>
                <div class='matrix-cell'>
                    <span style='color:#ffd700; font-size:0.75rem'>{ah_h_pick}</span>
                    {fmt_pct(ah_h_prob, 55)}
                </div>
                <div class='matrix-cell'>
                    <span style='color:#ffd700; font-size:0.75rem'>{ah_a_pick}</span>
                    {fmt_pct(ah_a_prob, 55)}
                </div>
                <div class='matrix-cell' style='justify-content:right; font-size:0.7rem; color:#555'>源:{row.get('數據源')}</div>
            </div>
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

# ================= 主程式 =================
def main():
    st.sidebar.title("🛠️ 賽事篩選")
    
    df, source, err_msg = load_data()
    
    if df.empty:
        st.error(f"❌ 無數據，請運行後端。({source})")
        if err_msg:
            st.code(err_msg, language='text')
            st.caption("提示: 請檢查 GitHub Secrets 或 Streamlit Secrets 的 GCP Key 格式。")
        return

    st.sidebar.markdown("### 狀態")
    all_statuses = ['進行中', '未開賽', '完場', '延期']
    selected_statuses = st.sidebar.pills("選擇狀態", all_statuses, default=['進行中', '未開賽'], selection_mode="multi")
    
    if '聯賽' in df.columns:
        st.sidebar.markdown("### 聯賽")
        all_leagues = sorted(df['聯賽'].unique().tolist())
        selected_leagues = st.sidebar.multiselect("選擇聯賽", all_leagues, default=all_leagues)
    else: selected_leagues = []

    hk_tz = pytz.timezone('Asia/Hong_Kong')
    now = datetime.now(hk_tz)
    st.caption(f"數據源: {source} | 更新: {now.strftime('%H:%M')}")

    filtered_df = df.copy()
    if selected_statuses:
        filtered_df = filtered_df[filtered_df['狀態'].isin(selected_statuses)]
    if selected_leagues:
        filtered_df = filtered_df[filtered_df['聯賽'].isin(selected_leagues)]

    status_order = {'進行中': 0, '未開賽': 1, '完場': 2, '延期': 3}
    filtered_df['status_rank'] = filtered_df['狀態'].map(status_order).fillna(4)
    filtered_df = filtered_df.sort_values(by=['status_rank', '時間'])

    if not filtered_df.empty:
        for _, row in filtered_df.iterrows():
            render_match_card(row)
    else:
        st.info("暫無符合條件的賽事")

if __name__ == "__main__":
    main()
