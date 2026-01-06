import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import math
import os

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI全能預測", page_icon="⚽", layout="wide")

# ================= 數學大腦 (泊松分佈) =================
def calculate_probabilities(home_exp, away_exp):
    def poisson(k, lam):
        return (lam**k * math.exp(-lam)) / math.factorial(k)

    home_win_prob = 0
    draw_prob = 0
    away_win_prob = 0
    over_25_prob = 0
    under_25_prob = 0

    for h in range(6): 
        for a in range(6): 
            prob = poisson(h, home_exp) * poisson(a, away_exp)
            if h > a: home_win_prob += prob
            elif h == a: draw_prob += prob
            else: away_win_prob += prob
            
            if h + a > 2.5: over_25_prob += prob
            else: under_25_prob += prob

    return {
        "home_win": home_win_prob * 100,
        "draw": draw_prob * 100,
        "away_win": away_win_prob * 100,
        "over": over_25_prob * 100,
        "under": under_25_prob * 100
    }

# ================= 連接 Google Sheet =================
@st.cache_data(ttl=60) 
def load_data():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    try:
        if os.path.exists("key.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        else:
            try:
                if "gcp_service_account" in st.secrets:
                    creds_dict = st.secrets["gcp_service_account"]
                    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                else:
                    st.error("❌ 找不到 Key！請確認資料夾內有 key.json")
                    return None
            except FileNotFoundError:
                st.error("❌ 找不到 secrets.toml 且無 key.json")
                return None

        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        data = sheet.get_all_records()
        return pd.DataFrame(data)

    except Exception as e:
        st.error(f"連線錯誤: {e}")
        return None

# ================= 主程式 =================
def main():
    st.title("⚽ 足球賽事預測 (Ultimate Pro)")
    
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
        st.rerun()

    df = load_data()

    if df is None or df.empty:
        st.warning("⚠️ 暫時未能讀取數據，請檢查連線設定 (key.json) 或確認 Google Sheet 有資料。")
        return

    # 確保數據類型正確
    numeric_cols = ['主預測', '客預測', '主攻(H)', '主防(H)']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # --- 1. 聯賽過濾 ---
    # 先確認是否有「聯賽」欄位
    if '聯賽' in df.columns:
        leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
        selected_league = st.selectbox("選擇聯賽:", leagues)
        if selected_league != "全部":
            df = df[df['聯賽'] == selected_league]

    # --- 2. 狀態篩選 ---
    st.write("---") 
    view_option = st.radio(
        "選擇查看模式：",
        ["📅 未開賽 / 進行中", "✅ 已完場 (核對賽果)"],
        horizontal=True
    )

    if view_option == "✅ 已完場 (核對賽果)":
        display_df = df[df['狀態'] == '完場']
    else:
        display_df = df[df['狀態'] != '完場']

    # --- 3. 核心顯示邏輯 (包含日期分組) ---
    if display_df.empty:
        st.info("暫無此類別的賽事數據。")
    else:
        # === 重要：先按時間排序，這樣分組才不會亂 ===
        if '時間' in display_df.columns:
            display_df = display_df.sort_values(by='時間')

        current_date_header = None # 用來記錄當前的日期標題
        
        for index, row in display_df.iterrows():
            # --- 日期處理與分組標題 ---
            time_full = str(row['時間']) # 格式預期是 "YYYY-MM-DD HH:MM"
            try:
                # 切割出 日期 和 時間
                date_part = time_full.split(' ')[0] 
                time_part = time_full.split(' ')[1]
            except:
                # 萬一格式不對，做個防錯
                date_part = "其他日期"
                time_part = time_full

            # 如果這一行的日期 跟 上一行不同，就印出一個大標題
            if date_part != current_date_header:
                current_date_header = date_part
                st.markdown(f"### 🗓️ {current_date_header}") # <--- 日期大標題
                st.markdown("---")

            # --- 準備數據 ---
            status = row['狀態']
            status_color = "🔴" if "進行中" in status else "🟢" if "完場" in status else "⚪"
            
            exp_h = row.get('主預測', 0)
            exp_a = row.get('客預測', 0)
            
            probs = calculate_probabilities(exp_h, exp_a)
            
            p_home = f"{probs['home_win']:.0f}%"
            p_draw = f"{probs['draw']:.0f}%"
            p_away = f"{probs['away_win']:.0f}%"
            p_over = f"{probs['over']:.0f}%"
            p_under = f"{probs['under']:.0f}%"

            # AI 建議文字
            if probs['home_win'] > probs['away_win'] + 10:
                rec_text = f"🏆 主勝 ({p_home})"
            elif probs['away_win'] > probs['home_win'] + 10:
                rec_text = f"✈️ 客勝 ({p_away})"
            else:
                rec_text = f"⚖️ 勢均力敵 (和: {p_draw})"

            if probs['over'] > 55:
                ou_text = f"🔥 大球 ({p_over})"
            elif probs['under'] > 55:
                ou_text = f"🧊 細球 ({p_under})"
            else:
                ou_text = f"中位數 ({p_over})"

            ai_analysis_text = f"""
            **🔮 AI 深度分析 (賽前預測)：**
            \n⚽ **預測比分**： {exp_h} : {exp_a}
            \n📊 **勝平負率**： 主勝 **{p_home}** | 和 **{p_draw}** | 客勝 **{p_away}**
            \n🎲 **大細機率**： 大球 (>2.5) **{p_over}** | 細球 (<2.5) **{p_under}**
            \n💡 **AI 建議**： **{rec_text}** |  **{ou_text}**
            """

            # --- 顯示卡片 ---
            with st.container():
                # 上方資訊列：時間 (只顯示 HH:MM) | 聯賽 | 狀態
                st.caption(f"🕒 {time_part} | {row['聯賽']} | {status_color} {status}")
                
                c1, c2, c3 = st.columns([4, 2, 4])
                with c1: 
                    st.markdown(f"**{row['主隊']}**", unsafe_allow_html=True)
                    # 嘗試顯示排名 (如果有)
                    if row.get('主排名'): st.caption(f"排名: {row['主排名']}")
                    st.caption(f"主攻:{row.get('主攻(H)',0)}")
                with c2:
                    score = f"{row['主分']} - {row['客分']}"
                    st.markdown(f"<h3 style='text-align: center; margin:0;'>{score}</h3>", unsafe_allow_html=True)
                with c3:
                    st.markdown(f"<div style='text-align: right'><b>{row['客隊']}</b></div>", unsafe_allow_html=True)
                    # 嘗試顯示排名 (如果有)
                    if row.get('客排名'): st.markdown(f"<div style='text-align: right; font-size: small; color: gray'>排名: {row['客排名']}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='text-align: right; color: gray; font-size: small'>客攻:{row.get('客攻(A)',0)}</div>", unsafe_allow_html=True)

                if view_option == "✅ 已完場 (核對賽果)":
                    st.success(f"🏁 **全場賽果**：{row['主隊']} {score} {row['客隊']}")
                    st.info(ai_analysis_text)
                else:
                    st.info(ai_analysis_text)
                
                # 對賽往績
                h2h_info = row.get('H2H', 'N/A')
                st.caption(f"⚔️ 對賽往績: {h2h_info}")
                
                st.write("") # 加點空隙

if __name__ == "__main__":
    main()
