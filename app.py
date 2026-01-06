import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import math
import os

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" # 請確保你的 Google Sheet 名稱完全一致

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

# ================= 連接 Google Sheet (已修復：優先讀本地 Key) =================
@st.cache_data(ttl=60) 
def load_data():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    try:
        # 1. 優先嘗試讀取本地的 key.json (解決你剛才的報錯)
        if os.path.exists("key.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        
        # 2. 如果本地沒有，才嘗試讀取 Streamlit 雲端 Secrets (部署時用)
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

        # 連接 Google Sheet
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
        st.warning("⚠️ 暫時未能讀取數據，請檢查連線設定 (key.json)。")
        return

    # 確保數據類型正確
    numeric_cols = ['主預測', '客預測', '總球數', '主攻(H)', '主防(H)']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # --- 1. 聯賽過濾 ---
    leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
    selected_league = st.selectbox("選擇聯賽:", leagues)

    if selected_league != "全部":
        df = df[df['聯賽'] == selected_league]

    # --- 2. 【狀態篩選按鈕】(這是你想要的新功能) ---
    st.write("---") # 分隔線
    view_option = st.radio(
        "選擇查看模式：",
        ["📅 未開賽 / 進行中", "✅ 已完場 (核對賽果)"],
        horizontal=True
    )

    # --- 3. 根據按鈕篩選數據 ---
    if view_option == "✅ 已完場 (核對賽果)":
        # 只保留狀態是 '完場' 的
        display_df = df[df['狀態'] == '完場']
    else:
        # 保留狀態 '不是' 完場的 (即 未開賽 或 進行中)
        display_df = df[df['狀態'] != '完場']

    # --- 顯示卡片 (Loop display_df) ---
    if display_df.empty:
        st.info("暫無此類別的賽事數據。")
    else:
        for index, row in display_df.iterrows():
            status = row['狀態']
            # 狀態顏色
            status_color = "🔴" if "進行中" in status else "🟢" if "完場" in status else "⚪"
            
            exp_h = row.get('主預測', 0)
            exp_a = row.get('客預測', 0)
            
            # 數學機率計算
            probs = calculate_probabilities(exp_h, exp_a)
            
            p_home = f"{probs['home_win']:.0f}%"
            p_draw = f"{probs['draw']:.0f}%"
            p_away = f"{probs['away_win']:.0f}%"
            p_over = f"{probs['over']:.0f}%"
            p_under = f"{probs['under']:.0f}%"

            # 判斷文字
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

            # --- 介面顯示 ---
            with st.container():
                st.markdown("---")
                st.caption(f"{row['時間']} | {row['聯賽']} | {status_color} {status}")
                
                c1, c2, c3 = st.columns([4, 2, 4])
                with c1: 
                    st.markdown(f"**{row['主隊']}**", unsafe_allow_html=True)
                    st.caption(f"主攻:{row.get('主攻(H)',0)}")
                with c2:
                    # 顯示實際比分
                    score = f"{row['主分']} - {row['客分']}"
                    st.markdown(f"<h3 style='text-align: center; margin:0;'>{score}</h3>", unsafe_allow_html=True)
                with c3:
                    st.markdown(f"<div style='text-align: right'><b>{row['客隊']}</b></div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='text-align: right; color: gray; font-size: small'>客攻:{row.get('客攻(A)',0)}</div>", unsafe_allow_html=True)

                # --- 智能顯示邏輯 ---
                if view_option == "✅ 已完場 (核對賽果)":
                    # 【完場模式】：顯示簡單對比
                    st.success(f"**賽果核對**：實際比分 [{score}] vs AI預測 [{exp_h} : {exp_a}]")
                else:
                    # 【未完場模式】：顯示詳細預測
                    st.info(f"""
                    **🔮 AI 深度分析：**
                    \n⚽ **預測比分**： {exp_h} : {exp_a}
                    \n📊 **勝平負率**： 主勝 **{p_home}** | 和 **{p_draw}** | 客勝 **{p_away}**
                    \n🎲 **大細機率**： 大球 (>2.5) **{p_over}** | 細球 (<2.5) **{p_under}**
                    \n💡 **AI 建議**： **{rec_text}** |  **{ou_text}**
                    """)
                
                st.caption(f"⚔️ 對賽往績: {row.get('H2H', 'N/A')}")

if __name__ == "__main__":
    main()
