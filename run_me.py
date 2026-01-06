import requests
import pandas as pd
import time
import random
from datetime import datetime, timedelta
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ================= 設定區 =================
API_KEY = '531bb40a089446bdae76a019f2af3beb'
API_URL = 'https://api.football-data.org/v4/matches'
GOOGLE_SHEET_NAME = "數據上傳" # 確保跟你的 Sheet 名稱一致
COMPETITIONS = 'PL,PD,CL,SA,BL1,FL1' 

# ================= 連接 Google Sheet =================
def connect_google_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        # 確保 key.json 在同一資料夾
        creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        return sheet
    except Exception as e:
        print(f"❌ Google Sheet 連線失敗: {e}")
        return None

# ================= 核心邏輯 =================
def get_real_data():
    # === 這裡改了文字，確保你知道這是新版 ===
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 正在啟動新版抓取 (過去6天 ~ 未來3天)...")
    
    headers = {'X-Auth-Token': API_KEY}
    
    today = datetime.now()
    
    # 設定日期範圍：過去 6 天 ~ 未來 3 天 (總共 10 天，符合限制)
    start_date = (today - timedelta(days=6)).strftime('%Y-%m-%d')
    end_date = (today + timedelta(days=3)).strftime('%Y-%m-%d')
    
    params = {
        'dateFrom': start_date,
        'dateTo': end_date,
        'competitions': COMPETITIONS
    }

    try:
        response = requests.get(API_URL, headers=headers, params=params)
        
        if response.status_code != 200:
            print(f"❌ API 請求失敗 (Code: {response.status_code}): {response.text}")
            return []

        data = response.json()
        matches = data.get('matches', [])
        
        if not matches:
            print(f"⚠️ 這段時間 ({start_date} ~ {end_date}) 找不到比賽數據。")
            return []

        cleaned_data = []
        hk_tz = pytz.timezone('Asia/Hong_Kong')

        for match in matches:
            # 1. 時間處理
            utc_str = match['utcDate']
            utc_dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ")
            utc_dt = utc_dt.replace(tzinfo=pytz.utc)
            hk_dt = utc_dt.astimezone(hk_tz)
            time_str = hk_dt.strftime('%Y-%m-%d %H:%M') 

            # 2. 狀態
            status_raw = match['status']
            status = '未開賽'
            if status_raw in ['IN_PLAY', 'PAUSED']: status = '進行中'
            elif status_raw == 'FINISHED': status = '完場'
            
            # 3. 比分
            score_h = match['score']['fullTime']['home']
            score_a = match['score']['fullTime']['away']
            if score_h is None and status == '進行中':
                    score_h = match['score']['duration']

            # 4. 模擬預測
            fake_home_exp = round(random.uniform(0.8, 2.5), 2)
            fake_away_exp = round(random.uniform(0.6, 2.0), 2)

            match_info = {
                '時間': time_str,
                '聯賽': match['competition']['name'],
                '主隊': match['homeTeam']['shortName'] or match['homeTeam']['name'],
                '客隊': match['awayTeam']['shortName'] or match['awayTeam']['name'],
                '主排名': '', 
                '客排名': '',
                '主近況': 'N/A',
                '客近況': 'N/A',
                '主預測': fake_home_exp,
                '客預測': fake_away_exp,
                '總球數': round(fake_home_exp + fake_away_exp, 1),
                '主攻(H)': round(fake_home_exp * 1.2, 1),
                '客攻(A)': round(fake_away_exp * 1.1, 1),
                '狀態': status,
                '主分': score_h if score_h is not None else '',
                '客分': score_a if score_a is not None else '',
                'H2H': 'N/A'
            }
            cleaned_data.append(match_info)
            
        print(f"✅ 成功抓取 {len(cleaned_data)} 場賽事！")
        return cleaned_data

    except Exception as e:
        print(f"⚠️ 執行錯誤: {e}")
        return []

# ================= 主程式 Loop =================
def main():
    print("🚀 【新版程式 run_me.py】已啟動！")
    while True:
        real_data = get_real_data()
        
        if real_data:
            df = pd.DataFrame(real_data)
            cols = ['時間', '聯賽', '主隊', '客隊', '主排名', '客排名', '主近況', '客近況', 
                    '主預測', '客預測', '總球數', '主攻(H)', '客攻(A)', '狀態', '主分', '客分', 'H2H']
            df = df.reindex(columns=cols, fill_value='')
            
            # 準備上傳
            header = df.columns.values.tolist()
            values = df.astype(str).values.tolist()
            data_to_upload = [header] + values

            sheet = connect_google_sheet()
            if sheet:
                try:
                    print(f"🚀 正在上傳 {len(values)} 筆資料到 Google Sheet...")
                    sheet.clear()
                    sheet.update(range_name='A1', values=data_to_upload)
                    print(f"☁️ Google Sheet 更新成功！")
                except Exception as e:
                    print(f"❌ 上傳失敗: {e}")
        else:
            print("⚠️ 無數據。")

        print("⏳ 等待 120 秒...\n")
        time.sleep(120)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("程式已停止。")