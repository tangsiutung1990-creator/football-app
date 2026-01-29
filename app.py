# app.py
import streamlit as st
from football import FootballApp
import pandas as pd

# --- 頁面設置 ---
st.set_page_config(page_title="英超 AI 足球預測", layout="wide", page_icon="⚽")

# --- 自定義 CSS (黑色背景與樣式) ---
st.markdown("""
    <style>
    /* 強制黑色背景 */
    .stApp {
        background-color: #000000;
        color: #ffffff;
    }
    /* 調整文字顏色為白色 */
    h1, h2, h3, h4, h5, h6, p, div, span, label {
        color: #e0e0e0 !important;
    }
    /* 卡片樣式 */
    .match-card {
        background-color: #1e1e1e;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #333;
        margin-bottom: 20px;
    }
    .team-name {
        font-size: 24px;
        font-weight: bold;
        color: #4CAF50 !important;
    }
    .stat-box {
        background-color: #2c2c2c;
        padding: 10px;
        border-radius: 5px;
        margin: 5px 0;
    }
    .warning {
        color: #ff4b4b !important;
        font-weight: bold;
    }
    /* 預測按鈕樣式 */
    .stButton>button {
        background-color: #4CAF50;
        color: white !important;
        border-radius: 5px;
        width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 初始化 ---
# 請在下方引號內填入你的 API KEY
API_KEY = "你的_API_KEY_填在這裡" 
app_logic = FootballApp(API_KEY)

st.title("⚽ 英超賽事 AI 預測中心")

# --- 側邊欄 / 頂部篩選 ---
status_filter = st.radio(
    "賽事狀態篩選",
    ("未開賽 (NS)", "已結束 (FT)", "取消/延後 (PST/CANC)"),
    horizontal=True
)

# --- 獲取數據 ---
with st.spinner('正在從英格蘭連線獲取最新數據...'):
    fixtures = app_logic.fetch_fixtures()

# 根據狀態篩選數據
filtered_fixtures = []
for f in fixtures:
    status = f['fixture']['status']['short']
    if status_filter.startswith("未開賽") and status in ['NS', 'TBD']:
        filtered_fixtures.append(f)
    elif status_filter.startswith("已結束") and status in ['FT', 'AET', 'PEN']:
        filtered_fixtures.append(f)
    elif status_filter.startswith("取消") and status in ['PST', 'CANC', 'ABD']:
        filtered_fixtures.append(f)

if not filtered_fixtures:
    st.info("目前沒有符合條件的賽事數據 (昨天/今天/明天)。")

# --- 顯示賽事 ---
for match in filtered_fixtures:
    # 提取基本資訊
    home_team = match['teams']['home']['name']
    away_team = match['teams']['away']['name']
    match_time = match['fixture']['date'].replace("T", " ")[:16] # 簡單格式化
    match_status = match['fixture']['status']['long']
    
    # 佈局：左邊球隊，右邊預測
    with st.container():
        st.markdown(f'<div class="match-card">', unsafe_allow_html=True)
        col1, col2 = st.columns([1, 2])
        
        # --- 左側：球隊資訊 ---
        with col1:
            st.markdown(f"<div style='text-align:center'>", unsafe_allow_html=True)
            st.image(match['teams']['home']['logo'], width=80)
            st.markdown(f"<p class='team-name'>{home_team}</p>", unsafe_allow_html=True)
            st.markdown("VS")
            st.markdown(f"<p class='team-name'>{away_team}</p>", unsafe_allow_html=True)
            st.image(match['teams']['away']['logo'], width=80)
            st.markdown(f"<p style='color:#aaa'>時間 (HKT): {match_time}</p>", unsafe_allow_html=True)
            st.markdown(f"<p>狀態: {match_status}</p>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

            # 顯示簡單陣容/傷兵 (模擬數據，真實API需額外調用)
            with st.expander("查看陣容與傷兵狀態"):
                st.write("🏥 主隊傷兵: 暫無重大傷停")
                st.write("🏥 客隊傷兵: 1名主力中場存疑")

        # --- 右側：AI 預測資訊 ---
        with col2:
            st.subheader("📊 賽事分析數據")
            
            # 按鈕觸發詳細預測
            if st.button(f"🤖 AI 預測 ({home_team} vs {away_team})", key=match['fixture']['id']):
                # 獲取預測數據
                pred = app_logic.ai_prediction_engine(match)
                
                # 1. 主客和機率
                st.markdown("#### 1. 勝率預測")
                p_col1, p_col2, p_col3 = st.columns(3)
                p_col1.metric("主勝", f"{pred['win_probs']['home']}%")
                p_col2.metric("和局", f"{pred['win_probs']['draw']}%")
                p_col3.metric("客勝", f"{pred['win_probs']['away']}%")
                
                # 5. 爆冷警告
                if pred['upset_alert']:
                    st.markdown(f"<p class='warning'>{pred['upset_alert']}</p>", unsafe_allow_html=True)

                # 9. 爭勝心
                st.info(f"💡 戰意分析: {pred['motivation']}")

                # 數據表格化展示 (2, 3, 4, 7, 8)
                tab1, tab2, tab3 = st.tabs(["盤口分析", "入球大小", "賽季數據"])
                
                with tab1:
                    st.markdown("**2. 亞洲盤機率 (主/客)**")
                    st.markdown(f"- 平手盤: {pred['asian_handicap']['level']}")
                    st.markdown(f"- 讓球 (-1/+1): {pred['asian_handicap']['minus_1']} / {pred['asian_handicap']['plus_1']}")
                    st.markdown(f"- 讓球 (-2/+2): {pred['asian_handicap']['minus_2']} / {pred['asian_handicap']['plus_2']}")

                with tab2:
                    st.markdown("**3. 全場入球大機率**")
                    cols = st.columns(5)
                    for idx, (k, v) in enumerate(pred['goals_over'].items()):
                        cols[idx].metric(f">{k}球", f"{v}%")
                    
                    st.markdown("**4. 半場入球大機率**")
                    h_cols = st.columns(3)
                    for idx, (k, v) in enumerate(pred['ht_goals'].items()):
                        h_cols[idx].metric(f"半場 >{k}", f"{v}%")

                with tab3:
                    st.markdown("**6-8. 賽季大數據觀察**")
                    st.markdown(f"- 🏟️ **{home_team} (主場)**: 主場勝率 65%, 入球大2.5機率 70%")
                    st.markdown(f"- ✈️ **{away_team} (客場)**: 客場勝率 40%, 入球大2.5機率 55%")
                    st.progress(65, text="主隊主場強勢度")
                    st.progress(40, text="客隊客場抗壓度")
            
            else:
                st.write("點擊上方按鈕以獲取詳細 AI 分析報告...")

        st.markdown('</div>', unsafe_allow_html=True)
