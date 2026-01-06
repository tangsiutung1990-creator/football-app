import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳"
JSON_KEY_FILE = "key.json" 

st.set_page_config(page_title="足球AI全能預測", page_icon="⚽", layout="wide")

# ================= 連接 Google Sheet =================
@st.cache_data(ttl=60) 
def load_data():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        return None

# ================= 主程式 =================
def main():
    st.title("⚽ 足球賽事預測 (Ultimate)")
    
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
        st.rerun()

    df = load_data()

    if df is None or df.empty:
        st.warning("⚠️ 暫時未能讀取數據，請稍後再試。")
        return

    # 確保數據類型正確
    numeric_cols = ['主預測', '客預測', '總球數', '主攻(H)', '主防(H)']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # 過濾器
    leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
    selected_league = st.selectbox("選擇聯賽:", leagues)

    if selected_league != "全部":
        df = df[df['聯賽'] == selected_league]

    # --- 顯示卡片 ---
    for index, row in df.iterrows():
        status = row['狀態']
        status_color = "🔴" if "進行中" in status else "🟢" if "完場" in status else "⚪"
        
        # 獲取預測數值
        exp_h = row.get('主預測', 0)
        exp_a = row.get('客預測', 0)
        total_goals = row.get('總球數', 0)
        
        # --- 判斷邏輯 ---
        # 1. 大細球判斷
        ou_str = "(中)"
        if total_goals >= 2.8: ou_str = "(🔥大)"
        elif total_goals <= 2.2: ou_str = "(🧊細)"
        
        # 2. 勝平負判斷 (當一方比另一方多 0.4 球以上視為有優勢)
        result_rec = "⚖️ 勢均力敵"
        if exp_h > exp_a + 0.4:
            result_rec = f"🏆 主勝 ({row['主隊']})"
        elif exp_a > exp_h + 0.4:
            result_rec = f"✈️ 客勝 ({row['客隊']})"

        with st.container():
            st.markdown("---")
            st.caption(f"{row['時間']} | {row['聯賽']} | {status_color} {status}")
            
            # 第一行：球隊與比分
            c1, c2, c3 = st.columns([4, 2, 4])
            with c1: 
                st.markdown(f"**{row['主隊']}**", unsafe_allow_html=True)
                st.caption(f"主攻:{row.get('主攻(H)',0)}")
            with c2:
                score = f"{row['主分']} - {row['客分']}"
                st.markdown(f"<h3 style='text-align: center; margin:0;'>{score}</h3>", unsafe_allow_html=True)
            with c3:
                st.markdown(f"<div style='text-align: right'><b>{row['客隊']}</b></div>", unsafe_allow_html=True)
                st.markdown(f"<div style='text-align: right; color: gray; font-size: small'>客攻:{row.get('客攻(A)',0)}</div>", unsafe_allow_html=True)

            # 第二行：AI 全能預測 (重點顯示區)
            st.info(f"""
            **🔮 AI 預測數據：**
            \n⚽ **預測比分**： {exp_h} : {exp_a}
            \n📊 **預測球數**： {total_goals} {ou_str}
            \n💡 **勝負建議**： **{result_rec}**
            """)
            
            # H2H 小字顯示
            st.caption(f"⚔️ 對賽往績 (主-和-客): {row.get('H2H', 'N/A')}")

if __name__ == "__main__":
    main()
