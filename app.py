import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ================= 設定區 =================
# 這裡要換成你的 Google Sheet 名稱
GOOGLE_SHEET_NAME = "數據上傳"
JSON_KEY_FILE = "key.json" # 確保 key.json 和 app.py 在同一資料夾

# 頁面設定 (手機友善)
st.set_page_config(page_title="足球AI預測", page_icon="⚽", layout="wide")

# ================= 連接 Google Sheet =================
@st.cache_data(ttl=60) # 每 60 秒緩存一次，避免瘋狂 Call Google
def load_data():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        data = sheet.get_all_records() # 讀取所有數據
        return pd.DataFrame(data)
    except Exception as e:
        return None

# ================= 主程式 =================
def main():
    st.title("⚽ 足球賽事預測 (Pro)")
    
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
        st.rerun()

    df = load_data()

    if df is None or df.empty:
        st.warning("⚠️ 暫時未能讀取數據，或者 Google Sheet 是空的。")
        return

    # 確保數據類型正確 (防止數字變文字)
    cols_to_convert = ['主攻(H)', '主防(H)', '客攻(A)', '客防(A)', '預測入球']
    for col in cols_to_convert:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # --- 過濾器 (可選) ---
    leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
    selected_league = st.selectbox("選擇聯賽:", leagues)

    if selected_league != "全部":
        df = df[df['聯賽'] == selected_league]

    # --- 顯示卡片 ---
    for index, row in df.iterrows():
        # 樣式處理
        status = row['狀態']
        status_color = "🔴" if "進行中" in status else "🟢" if "完場" in status else "⚪"
        
        with st.container():
            st.markdown("---")
            # 第一行：時間 + 聯賽 + 狀態
            st.caption(f"{row['時間']} | {row['聯賽']} | {status_color} {status}")
            
            # 第二行：比分 (大字體)
            c1, c2, c3 = st.columns([4, 2, 4])
            with c1: 
                st.markdown(f"**{row['主隊']}**", unsafe_allow_html=True)
                st.caption(f"主攻:{row.get('主攻(H)',0)} / 防:{row.get('主防(H)',0)}")
            with c2:
                score = f"{row['主分']} - {row['客分']}"
                st.markdown(f"<h3 style='text-align: center; margin:0;'>{score}</h3>", unsafe_allow_html=True)
            with c3:
                st.markdown(f"<div style='text-align: right'><b>{row['客隊']}</b></div>", unsafe_allow_html=True)
                st.markdown(f"<div style='text-align: right; color: gray; font-size: small'>攻:{row.get('客攻(A)',0)} / 防:{row.get('客防(A)',0)}</div>", unsafe_allow_html=True)

            # 第三行：預測數據 (重點)
            m1, m2 = st.columns(2)
            with m1:
                st.info(f"📊 預測球數: **{row.get('預測入球', 'N/A')}**")
            with m2:
                # 簡單分析 H2H
                h2h = str(row.get('H2H (主-和-客)', 'N/A'))
                st.warning(f"⚔️ 往績: {h2h}")

            # 簡單的大細球建議 (如果預測球數 > 2.8 則提示大球)
            try:
                pred = float(row.get('預測入球', 0))
                if pred >= 3.0:
                    st.markdown("🔥 **AI 建議: 大球機會高**")
                elif pred <= 2.0:
                    st.markdown("🧊 **AI 建議: 細球機會高**")
            except:
                pass

if __name__ == "__main__":
    main()
