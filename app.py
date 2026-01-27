import streamlit as st
import os
import json
import pandas as pd
from datetime import datetime
import pytz

# ================= 1. 安全啟動與函式庫檢查 =================
try:
    import gspread
    from google.oauth2.service_account import Credentials # 改用新版庫
except ImportError as e:
    st.error("❌ 缺少必要函式庫。請確認 requirements.txt 包含: gspread, google-auth")
    st.stop()

st.set_page_config(page_title="足球AI Pro", page_icon="⚽", layout="wide")

# ================= 2. 設定與 CSS =================
GOOGLE_SHEET_NAME = "數據上傳" 
CSV_FILENAME = "football_data_backup.csv" 
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    .compact-card { background-color: #1a1c24; border: 1px solid #333; border-radius: 6px; padding: 2px 4px; margin-bottom: 6px; }
    .match-header { display: flex; justify-content: space-between; color: #999; font-size: 0.8rem; border-bottom: 1px solid #333; }
    .team-name { font-weight: bold; font-size: 1.1rem; color: #fff; } 
    .score-main { font-size: 1.8rem; font-weight: bold; color: #00ffea; text-align: right; }
    .matrix-cell { display: flex; justify-content: space-between; padding: 0 1px; color: #ddd; font-size: 0.8rem; }
    .cell-high { color: #00ff00; font-weight: bold; }
    .cell-mid { color: #ffff00; }
    .status-live { color: #ff4b4b; font-weight: bold; }
    .status-ft { color: #00ffea; }
    section[data-testid="stSidebar"] { width: 220px !important; }
</style>
""", unsafe_allow_html=True)

# ================= 3. 核心工具 =================

def clean_pct(val):
    try: return int(float(str(val).replace('%', '')))
    except: return 0

def fmt_pct(val, threshold=50):
    v = clean_pct(val)
    if v == 0: return "-"
    color_cls = 'cell-high' if v >= threshold else ('cell-mid' if v >= threshold - 10 else '')
    return f"<span class='{color_cls}'>{v}%</span>"

def fix_private_key(key_str):
    """修復 Key 的換行與格式問題"""
    if not key_str: return None
    fixed_key = str(key_str).strip()
    
    # 移除前後多餘的引號
    if fixed_key.startswith("'") and fixed_key.endswith("'"): fixed_key = fixed_key[1:-1]
    if fixed_key.startswith('"') and fixed_key.endswith('"'): fixed_key = fixed_key[1:-1]
    
    # 處理轉義符號
    fixed_key = fixed_key.replace("\\\\n", "\n").replace("\\n", "\n").replace("\r", "")
    
    return fixed_key

@st.cache_resource(ttl=600) 
def get_google_sheet_data():
    creds = None
    debug_log = []
    
    # === 1. 嘗試環境變量 ===
    json_text = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
    if json_text:
        try:
            info = json.loads(json_text)
            if 'private_key' in info: info['private_key'] = fix_private_key(info['private_key'])
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
            debug_log.append("✅ Env Var Loaded")
        except Exception as e:
            debug_log.append(f"❌ Env Var Error: {e}")

    # === 2. 嘗試 Secrets (Google Auth 新版寫法) ===
    if not creds:
        try:
            if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
                # 轉成標準 Dict
                info = dict(st.secrets["gcp_service_account"])
                
                # 修復 Key
                if 'private_key' in info:
                    info['private_key'] = fix_private_key(info['private_key'])
                
                # 使用新版庫加載
                creds = Credentials.from_service_account_info(info, scopes=SCOPES)
                debug_log.append(f"✅ Secrets Loaded (Email: {info.get('client_email')})")
        except Exception as e:
            debug_log.append(f"❌ Secrets Error: {e}")

    # === 3. 本地檔案 ===
    if not creds and os.path.exists("key.json"):
        try:
            creds = Credentials.from_service_account_file("key.json", scopes=SCOPES)
            debug_log.append("✅ Local Key Loaded")
        except Exception as e:
            debug_log.append(f"❌ Local Key Error: {e}")

    # === 連接 gspread ===
    if creds:
        try:
            client = gspread.authorize(creds)
            sheet = client.open(GOOGLE_SHEET_NAME).sheet1
            return pd.DataFrame(sheet.get_all_records()), "Cloud", debug_log
        except Exception as e:
            # 這裡最常見的是: 試算表沒開權限給機器人 Email
            debug_log.append(f"🔥 Auth OK but Sheet Fail: {e}")
            return pd.DataFrame(), "Auth Error", debug_log
    
    return pd.DataFrame(), "None", debug_log

def load_data():
    df = pd.DataFrame()
    source = "無"
    debug_log = []
    try:
        df, source, debug_log = get_google_sheet_data()
    except Exception as e:
        debug_log.append(f"🔥 Critical Error: {e}")
    
    # Fallback
    if (df.empty or "Error" in source) and os.path.exists(CSV_FILENAME):
        try:
            df = pd.read_csv(CSV_FILENAME)
            source = f"Local Backup (CSV) - Cloud: {source}"
        except: pass
    return df, source, debug_log

def render_match_card(row):
    # (保持原本的渲染邏輯)
    prob_h = clean_pct(row.get('主勝率', 0))
    prob_d = clean_pct(row.get('和率', 0))
    prob_a = clean_pct(row.get('客勝率', 0))
    score_txt = f"{row.get('主分')} - {row.get('客分')}" if str(row.get('主分')) not in ['','nan'] else "VS"
    xg_txt = f"xG: {row.get('xG主',0)} - {row.get('xG客',0)}"
    status = row.get('狀態')
    status_cls = "status-live" if status == '進行中' else ("status-ft" if status == '完場' else "")
    ah_h_pick = row.get('亞盤主', '-'); ah_h_prob = row.get('亞盤主率', 0)
    ah_a_pick = row.get('亞盤客', '-'); ah_a_prob = row.get('亞盤客率', 0)
    
    card_html = f"""
    <div class='compact-card'>
        <div class='match-header'><span>{row.get('時間')} | {row.get('聯賽')}</span><span class='{status_cls}'>{status}</span></div>
        <div class='content-row'>
            <div class='teams-area'>
                <div class='team-name'>{row.get('主隊')} <small style='color:#666; font-size:0.8rem'>#{row.get('主排名')}</small></div>
                <div class='team-name'>{row.get('客隊')} <small style='color:#666; font-size:0.8rem'>#{row.get('客排名')}</small></div>
            </div>
            <div class='score-area'><div class='score-main'>{score_txt}</div><div class='score-sub'>{xg_txt}</div></div>
        </div>
        <div class='grid-matrix'>
            <div class='matrix-col'><div class='matrix-cell'><span class='matrix-label'>主</span>{fmt_pct(prob_h)} {row.get('主Value','')}</div><div class='matrix-cell'><span class='matrix-label'>和</span>{fmt_pct(prob_d)} {row.get('和Value','')}</div><div class='matrix-cell'><span class='matrix-label'>客</span>{fmt_pct(prob_a)} {row.get('客Value','')}</div></div>
            <div class='matrix-col'><div class='matrix-cell'><span class='matrix-label'>>1.5</span>{fmt_pct(row.get('大1.5'), 75)}</div><div class='matrix-cell'><span class='matrix-label'>>2.5</span>{fmt_pct(row.get('大2.5'), 55)}</div></div>
            <div class='matrix-col'><div class='matrix-cell'><span class='matrix-label'>半>0.5</span>{fmt_pct(row.get('半大0.5'), 65)}</div><div class='matrix-cell'><span class='matrix-label'>BTTS</span>{fmt_pct(row.get('BTTS'), 55)}</div></div>
            <div class='matrix-col'><div class='matrix-cell'><span style='color:#ffd700; font-size:0.75rem'>{ah_h_pick}</span>{fmt_pct(ah_h_prob, 55)}</div><div class='matrix-cell'><span style='color:#ffd700; font-size:0.75rem'>{ah_a_pick}</span>{fmt_pct(ah_a_prob, 55)}</div></div>
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

def main():
    st.sidebar.title("🛠️ 賽事篩選")
    df, source, debug_log = load_data()
    
    if df.empty and "Local" not in source:
        st.error("❌ 無法加載數據")
        with st.expander("詳細錯誤日誌 (Debug)", expanded=True):
            for log in debug_log: st.write(log)
        return

    if "Local" in source or "Error" in source:
        st.warning(f"⚠️ 使用本地備份數據 ({source})")
        with st.expander("☁️ 雲端連線診斷"):
            for log in debug_log: st.write(log)

    st.sidebar.markdown("### 狀態")
    all_statuses = ['進行中', '未開賽', '完場', '延期']
    selected_statuses = st.sidebar.pills("選擇狀態", all_statuses, default=['進行中', '未開賽'], selection_mode="multi")
    
    if '聯賽' in df.columns:
        all_leagues = sorted(df['聯賽'].unique().tolist())
        selected_leagues = st.sidebar.multiselect("選擇聯賽", all_leagues, default=all_leagues)
    else: selected_leagues = []

    hk_tz = pytz.timezone('Asia/Hong_Kong')
    now = datetime.now(hk_tz)
    st.caption(f"數據源: {source} | 更新: {now.strftime('%H:%M')}")

    filtered_df = df.copy()
    if selected_statuses: filtered_df = filtered_df[filtered_df['狀態'].isin(selected_statuses)]
    if selected_leagues: filtered_df = filtered_df[filtered_df['聯賽'].isin(selected_leagues)]

    status_order = {'進行中': 0, '未開賽': 1, '完場': 2, '延期': 3}
    if '狀態' in filtered_df.columns:
        filtered_df['status_rank'] = filtered_df['狀態'].map(status_order).fillna(4)
        filtered_df = filtered_df.sort_values(by=['status_rank', '時間'])

    if not filtered_df.empty:
        for _, row in filtered_df.iterrows(): render_match_card(row)
    else:
        st.info("暫無符合條件的賽事")

if __name__ == "__main__":
    main()
