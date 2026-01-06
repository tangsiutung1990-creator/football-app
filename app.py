import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import math

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳"
JSON_KEY_FILE = "key.json" 

st.set_page_config(page_title="足球AI全能預測", page_icon="⚽", layout="wide")

# ================= 數學大腦 (泊松分佈計算機率) =================
def calculate_probabilities(home_exp, away_exp):
    """
    輸入: 主隊預計入球, 客隊預計入球
    輸出: 主勝率, 和局率, 客勝率, 大球率(>2.5), 細球率(<2.5)
    """
    # 簡單的泊松函數
    def poisson(k, lam):
        return (lam**k * math.exp(-lam)) / math.factorial(k)

    # 模擬 0-0 到 5-5 的所有比分機率
    home_win_prob = 0
    draw_prob = 0
    away_win_prob = 0
    over_25_prob = 0
    under_25_prob = 0

    for h in range(6): # 主隊入 0-5 球
        for a in range(6): # 客隊入 0-5 球
            prob = poisson(h, home_exp) * poisson(a, away_exp)
            
            # 累加勝平負機率
            if h > a: home_win_prob += prob
            elif h == a: draw_prob += prob
            else: away_win_prob += prob
            
            # 累加大細球機率
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
    st.title("⚽ 足球賽事預測 (Ultimate Pro)")
    
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
        
        # --- 🔥 呼叫數學大腦計算機率 🔥 ---
        probs = calculate_probabilities(exp_h, exp_a)
        
        # 格式化機率顯示 (例如: 45%)
        p_home = f"{probs['home_win']:.0f}%"
        p_draw = f"{probs['draw']:.0f}%"
        p_away = f"{probs['away_win']:.0f}%"
        p_over = f"{probs['over']:.0f}%"
        p_under = f"{probs['under']:.0f}%"

        # 判斷勝負方向
        if probs['home_win'] > probs['away_win'] + 10: # 主勝率高過客勝 10%
            rec_text = f"🏆 主勝 ({p_home})"
        elif probs['away_win'] > probs['home_win'] + 10:
            rec_text = f"✈️ 客勝 ({p_away})"
        else:
            rec_text = f"⚖️ 勢均力敵 (和: {p_draw})"

        # 判斷大細方向
        if probs['over'] > 55:
            ou_text = f"🔥 大球 ({p_over})"
        elif probs['under'] > 55:
            ou_text = f"🧊 細球 ({p_under})"
        else:
            ou_text = f"中位數 ({p_over})"

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

            # 第二行：AI 全能預測 (加入機率顯示)
            st.info(f"""
            **🔮 AI 深度分析：**
            \n⚽ **預測比分**： {exp_h} : {exp_a}
            \n📊 **勝平負率**： 主勝 **{p_home}** | 和 **{p_draw}** | 客勝 **{p_away}**
            \n🎲 **大細機率**： 大球 (>2.5) **{p_over}** | 細球 (<2.5) **{p_under}**
            \n💡 **AI 建議**： **{rec_text}** |  **{ou_text}**
            """)
            
            # H2H 小字
            st.caption(f"⚔️ 對賽往績: {row.get('H2H', 'N/A')}")

if __name__ == "__main__":
    main()
