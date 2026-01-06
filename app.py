import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import math
import os

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳"
CSV_FILE = "football_data.csv" # bot.py 生成的檔案

st.set_page_config(page_title="足球AI全能預測 (Pro)", page_icon="⚽", layout="wide")

# ================= 工具：繪製紅綠燈 (Form Guide) =================
def render_form_guide(form_str):
    """將 'W,D,L' 轉換成 HTML 彩色豆豆"""
    if not isinstance(form_str, str) or not form_str: return ""
    
    html = ""
    # 移除空格並分割
    results = form_str.replace(" ", "").split(",")
    # 只取最後 5 場
    results = results[-5:]
    
    for res in results:
        color = "#ccc"
        if res == 'W': color = "#2ecc71" # 綠 (勝)
        elif res == 'D': color = "#f1c40f" # 黃 (和)
        elif res == 'L': color = "#e74c3c" # 紅 (負)
        
        html += f'''
        <span style="
            display:inline-block; width:10px; height:10px; 
            background-color:{color}; border-radius:50%; margin: 0 2px;
            border: 1px solid #555;" title="{res}">
        </span>
        '''
    return html

# ================= 數學大腦 (泊松分佈) =================
def calculate_probabilities(home_exp, away_exp):
    def poisson(k, lam):
        return (lam**k * math.exp(-lam)) / math.factorial(k)

    home_win_prob = 0; draw_prob = 0; away_win_prob = 0
    over_25_prob = 0; under_25_prob = 0

    for h in range(6): 
        for a in range(6): 
            prob = poisson(h, home_exp) * poisson(a, away_exp)
            if h > a: home_win_prob += prob
            elif h == a: draw_prob += prob
            else: away_win_prob += prob
            
            if h + a > 2.5: over_25_prob += prob
            else: under_25_prob += prob

    return {
        "home_win": home_win_prob * 100, "draw": draw_prob * 100, "away_win": away_win_prob * 100,
        "over": over_25_prob * 100, "under": under_25_prob * 100
    }

# ================= 智能數據讀取 =================
@st.cache_data(ttl=60) 
def load_data():
    # 1. 優先讀取 bot.py 生成的本地 CSV (為了讓你即刻見到紅綠燈效果)
    if os.path.exists(CSV_FILE):
        return pd.read_csv(CSV_FILE)
    
    # 2. 如果沒有 CSV，嘗試讀取 Google Sheet (後備方案)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if os.path.exists("key.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        else:
            # 雲端部署用
            if "gcp_service_account" in st.secrets:
                creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
            else:
                return None
        
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"數據讀取錯誤: {e}")
        return None

# ================= 主程式 =================
def main():
    st.title("⚽ 足球賽事預測 (Ultimate Pro)")
    
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
        st.rerun()

    df = load_data()

    if df is None or df.empty:
        st.warning("⚠️ 找不到數據！請先運行 bot.py 生成數據，或檢查 Google Sheet 連線。")
        return

    # 確保數值正確
    num_cols = ['主預測', '客預測', '總球數', '主排名', '客排名']
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # --- 1. 聯賽過濾 ---
    leagues = ["全部"] + sorted(list(set(df['聯賽'].astype(str))))
    selected_league = st.selectbox("選擇聯賽:", leagues)
    if selected_league != "全部":
        df = df[df['聯賽'] == selected_league]

    # --- 2. 狀態篩選按鈕 ---
    st.write("---")
    view_option = st.radio(
        "", 
        ["📅 未開賽 / 進行中", "✅ 已完場 (核對賽果)"], 
        horizontal=True
    )

    # --- 3. 篩選數據 ---
    if view_option == "✅ 已完場 (核對賽果)":
        display_df = df[df['狀態'] == '完場']
    else:
        display_df = df[df['狀態'] != '完場']

    # --- 顯示卡片 ---
    if display_df.empty:
        st.info("暫無此類別賽事。")
    else:
        for index, row in display_df.iterrows():
            status = row['狀態']
            status_color = "🔴" if "進行中" in status else "🟢" if "完場" in status else "⚪"
            
            # 準備數據
            exp_h = row.get('主預測', 0)
            exp_a = row.get('客預測', 0)
            probs = calculate_probabilities(exp_h, exp_a)
            
            # 準備 Form Guide (紅綠燈)
            form_h = render_form_guide(row.get('主近況', ''))
            form_a = render_form_guide(row.get('客近況', ''))
            rank_h = row.get('主排名', '-')
            rank_a = row.get('客排名', '-')

            # 準備分析文字
            p_home = f"{probs['home_win']:.0f}%"
            p_draw = f"{probs['draw']:.0f}%"
            p_away = f"{probs['away_win']:.0f}%"
            
            if probs['home_win'] > probs['away_win'] + 10: rec_text = f"🏆 主勝 ({p_home})"
            elif probs['away_win'] > probs['home_win'] + 10: rec_text = f"✈️ 客勝 ({p_away})"
            else: rec_text = f"⚖️ 勢均力敵 (和: {p_draw})"
            
            ou_text = f"🔥 大球 ({probs['over']:.0f}%)" if probs['over'] > 55 else f"🧊 細球 ({probs['under']:.0f}%)"

            ai_analysis = f"""
            **🔮 AI 賽前分析：**
            \n📊 **勝平負率**： 主 {p_home} | 和 {p_draw} | 客 {p_away}
            \n💡 **AI 建議**： {rec_text} | {ou_text}
            """

            # --- 介面渲染 ---
            with st.container():
                st.markdown("---")
                st.caption(f"{row['時間']} | {row['聯賽']} | {status_color} {status}")
                
                c1, c2, c3 = st.columns([4, 2, 4])
                
                # 主隊
                with c1:
                    st.caption(f"No.{rank_h}") # 排名
                    st.markdown(f"**{row['主隊']}**", unsafe_allow_html=True)
                    st.markdown(f"<div>{form_h}</div>", unsafe_allow_html=True) # 紅綠燈
                    st.caption(f"攻力:{row.get('主攻(H)',0)}")
                
                # 比分
                with c2:
                    score_display = f"{row['主分']} - {row['客分']}"
                    st.markdown(f"<h2 style='text-align: center; margin:0;'>{score_display}</h2>", unsafe_allow_html=True)
                
                # 客隊
                with c3:
                    st.markdown(f"<div style='text-align: right; font-size:0.8em; color:gray'>No.{rank_a}</div>", unsafe_allow_html=True) # 排名
                    st.markdown(f"<div style='text-align: right'><b>{row['客隊']}</b></div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='text-align: right'>{form_a}</div>", unsafe_allow_html=True) # 紅綠燈
                    st.markdown(f"<div style='text-align: right; color: gray; font-size: small'>攻力:{row.get('客攻(A)',0)}</div>", unsafe_allow_html=True)

                # 智能底部資訊
                if view_option == "✅ 已完場 (核對賽果)":
                    st.success(f"🏁 **全場賽果**：{row['主隊']} {score_display} {row['客隊']}")
                    with st.expander("查看當初 AI 預測 (覆盤用)"):
                        st.info(ai_analysis)
                else:
                    st.info(ai_analysis)
                
                st.caption(f"⚔️ {row.get('H2H', '')}")

if __name__ == "__main__":
    main()
