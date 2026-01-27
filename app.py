import streamlit as st
import os
import json
import pandas as pd
from datetime import datetime
import pytz

# ================= 1. 安全啟動檢查 =================
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
except ImportError as e:
    st.error(f"""
    ❌ 缺少必要函式庫。請確認 `requirements.txt` 包含: gspread, oauth2client
    錯誤: {e}
    """)
    st.stop()

st.set_page_config(page_title="足球AI Pro", page_icon="⚽", layout="wide")

# ================= 2. 設定與 CSS =================
GOOGLE_SHEET_NAME = "數據上傳" 
CSV_FILENAME = "football_data_backup.csv" 

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

# ================= 3. 核心邏輯 =================

def clean_pct(val):
    try: return int(float(str(val).replace('%', '')))
    except: return 0

def fmt_pct(val, threshold=50):
    v = clean_pct(val)
    if v == 0: return "-"
    color_cls = 'cell-high' if v >= threshold else ('cell-mid' if v >= threshold - 10 else '')
    return f"<span class='{color_cls}'>{v}%</span>"

def fix_private_key(key_str):
    """
    終極修復邏輯：處理各種引號包裹、轉義換行
    """
    if not key_str: return None
    
    # 1. 強制轉字串
    fixed_key = str(key_str).strip()
    
    # 2. 如果 Key 被額外的引號包住 (例如 "'-----BEGIN...'")，去除它們
    if fixed_key.startswith("'") and fixed_key.endswith("'"):
        fixed_key = fixed_key[1:-1]
    if fixed_key.startswith('"') and fixed_key.endswith('"'):
        fixed_key = fixed_key[1:-1]

    # 3. 處理換行：將 literal string "\n" 轉換為真正的換行字元
    # 先處理雙重轉義 (有些環境會變成 \\n)
    fixed_key = fixed_key.replace("\\\\n", "\n")
    # 再處理標準轉義
    fixed_key = fixed_key.replace("\\n", "\n")
    
    return fixed_key

def clean_json_string(json_str):
    if not json_str: return ""
    clean_str = json_str.strip()
    if clean_str.startswith("'") and clean_str.endswith("'"): clean_str = clean_str[1:-1]
    if clean_str.startswith('"') and clean_str.endswith('"') and len(clean_str) > 2 and clean_str[1] == '{': clean_str = clean_str[1:-1]
    return clean_str

@st.cache_resource(ttl=600) 
def get_google_sheet_data():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = None
    debug_log = []
    
    # === 方法 A: 環境變量 (GCP_SERVICE_ACCOUNT_JSON) ===
    json_text = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
    if json_text:
        try:
            json_text = clean_json_string(json_text)
            creds_dict = json.loads(json_text)
            if 'private_key' in creds_dict:
                creds_dict['private_key'] = fix_private_key(creds_dict['private_key'])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            debug_log.append(f"✅ Env Var Loaded")
        except Exception as e:
            debug_log.append(f"❌ Env Var Error: {str(e)}")

    # === 方法 B: Streamlit Secrets (gcp_service_account) ===
    if not creds:
        try:
            if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
                # 必須使用 dict() 拷貝，避免修改原始 secrets 導致快取問題
                creds_dict = dict(st.secrets["gcp_service_account"])
                
                # --- 診斷開始 ---
                raw_key = str(creds_dict.get('private_key', 'MISSING'))
                debug_log.append(f"🔍 [Diag] Raw Key Length: {len(raw_key)}")
                debug_log.append(f"🔍 [Diag] Raw Key Start: {raw_key[:20]}...") 
                # --- 診斷結束 ---

                if 'private_key' in creds_dict:
                    creds_dict['private_key'] = fix_private_key(creds_dict['private_key'])
                
                # 檢查修復後的 Key 是否有效
                final_key = creds_dict['private_key']
                if "-----BEGIN PRIVATE KEY-----" not in final_key:
                    debug_log.append("❌ [Fatal] Key 修復後仍缺少 PEM Header！請檢查 secrets.toml")
                else:
                    debug_log.append("✅ [Diag] Key Header Found")

                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                debug_log.append(f"✅ Secrets Loaded (Email: {creds_dict.get('client_email', 'Unknown')})")
        except Exception as e:
            debug_log.append(f"❌ Secrets Error: {str(e)}")

    # === 方法 C: 本地 key.json ===
    if not creds and os.path.exists("key.json"):
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
            debug_log.append("✅ Local Key Loaded")
        except Exception as e:
            debug_log.append(f"❌ Local Key Error: {str(e)}")

    # === 連接 ===
    if creds:
        try:
            client = gspread.authorize(creds)
            sheet = client.open(GOOGLE_SHEET_NAME).sheet1
            return pd.DataFrame(sheet.get_all_records()), "Cloud", debug_log
        except Exception as e:
            debug_log.append(f"🔥 Connect Fail: {str(e)}")
            return pd.DataFrame(), "Auth Error", debug_log
    
    return pd.DataFrame(), "None", debug_log

def load_data():
    df = pd.DataFrame()
    source = "無"
    debug_log = []
    try:
        df, source, debug_log = get_google_sheet_data()
    except Exception as e:
        debug_log.append(f"🔥 Global Connect Error: {str(e)}")
    
    # Fallback
    if (df.empty or "Error" in source) and os.path.exists(CSV_FILENAME):
        try:
            df = pd.read_csv(CSV_FILENAME)
            source = f"Local Backup (CSV) - Cloud: {source}"
        except: pass
    return df, source, debug_log

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
    
    # 錯誤攔截顯示
    if df.empty and "Local" not in source:
        st.error("❌ 無法加載數據，請查看下方診斷資訊。")
        with st.expander("詳細錯誤日誌 (Debug) - 請截圖此處", expanded=True):
            for log in debug_log: st.code(log, language='text')
        return

    if "Local" in source or "Error" in source:
        st.warning(f"⚠️ 使用本地備份數據 ({source})")
        with st.expander("☁️ 雲端連線診斷"):
            for log in debug_log: st.write(log)

    # 正常渲染
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
