import pandas as pd
import os
import random
from datetime import datetime

# 檔案名稱
FILE_NAME = 'football_data.csv'

def get_latest_data():
    """
    模擬從網上抓取的最新數據。
    將來請把你的爬蟲代碼放進這裡，並 return 一個 List of Dictionary。
    """
    # 這裡我們模擬一下：假設有些比賽正在踢，有些未開，有些完場
    # 注意：這裡的數據每次跑都會變一點點，方便你測試「更新」功能
    return [
        {'時間': '19:30', '主隊': '曼城', '客隊': '曼聯', '預測': '主勝', '狀態': '完場', '比分': '3-1'},
        {'時間': '22:00', '主隊': '利物浦', '客隊': '車路士', '預測': '大波', '狀態': '進行中', '比分': '1-1'},
        {'時間': '23:00', '主隊': '阿仙奴', '客隊': '熱刺', '預測': '主勝', '狀態': '未開賽', '比分': '-'},
        {'時間': '01:45', '主隊': '皇馬', '客隊': '巴塞', '預測': '客勝', '狀態': '未開賽', '比分': '-'},
    ]

def update_csv():
    # 1. 獲取最新數據
    new_data = get_latest_data()
    print(f"抓取到 {len(new_data)} 筆新數據...")

    # 2. 嘗試讀取舊數據
    if os.path.exists(FILE_NAME):
        try:
            df_old = pd.read_csv(FILE_NAME)
            existing_data = df_old.to_dict('records')
        except:
            existing_data = []
    else:
        existing_data = []

    # 3. 【核心邏輯】Upsert (更新或插入)
    # 我們用「主隊」作為唯一識別碼 (Key)，假設同一天主隊只踢一場
    processed_teams = set()
    
    # 先將舊數據放入一個字典，方便查找： { '曼城': {row_data}, ... }
    data_map = {row['主隊']: row for row in existing_data}

    # 用新數據更新舊數據
    for new_row in new_data:
        team = new_row['主隊']
        # 無論舊的有定冇，都用新的覆蓋 (因為新的狀態最準)
        data_map[team] = new_row
        processed_teams.add(team)

    # 將 Map 轉回 List
    final_data_list = list(data_map.values())

    # 4. 儲存
    df_final = pd.DataFrame(final_data_list)
    
    # 排序：為了美觀，我們可以按時間排序 (可選)
    # df_final = df_final.sort_values(by='時間')
    
    df_final.to_csv(FILE_NAME, index=False, encoding='utf-8-sig')
    print(f"✅ 更新完成！數據已儲存至 {FILE_NAME}")

if __name__ == "__main__":
    update_csv()
