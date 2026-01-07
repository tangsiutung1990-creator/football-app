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
BASE_URL = 'https://api.football-data.org/v4'
GOOGLE_SHEET_NAME = "數據上傳" 
COMPETITIONS = ['PL', 'PD', 'CL', 'SA', 'BL1', 'FL1'] # 英超, 西甲, 歐聯, 意甲, 德甲, 法甲

# ================= 連接 Google Sheet =================
def connect_google_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        return sheet
    except Exception as e:
        print(f"❌ Google Sheet 連線失敗: {e}")
        return None

# ================= 獲取聯賽排名 (維持原樣) =================
def get_all_standings():
    print("📊 正在獲取各聯賽實時排名...")
    standings_map = {}
    headers = {'X-Auth-Token': API_KEY}
    
    for comp in COMPETITIONS:
        try:
            url = f"{BASE_URL}/competitions/{comp}/standings"
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                for table in data.get('standings', []):
                    if table['type'] == 'TOTAL':
                        for entry in table['table']:
                            team_id = entry['team']['id']
                            raw_form = entry.get('form')
                            if raw_form is None: raw_form = "N/A"
                            standings_map[team_id] = {
                                'rank': entry['position'],
                                'form': raw_form,
                                'points': entry['points']
                            }
            time.sleep(2) 
        except Exception as e:
            print(f"⚠️ 無法獲取 {comp} 排名: {e}")
    return standings_map

# ================= 新增：獲取 H2H 對賽往績 =================
def get_h2h_data(match_id):
    headers = {'X-Auth-Token': API_KEY}
    url = f"{BASE_URL}/matches/{match_id}/head2head"
    
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            agg = data.get('aggregates', {})
            
            # 提取數據
            matches_played = agg.get('numberOfMatches', 0)
            h_wins = agg.get('homeTeam', {}).get('wins', 0)
            draws = agg.get('homeTeam', {}).get('draws', 0)
            a_wins = agg.get('awayTeam', {}).get('wins', 0)
            
            if matches_played == 0:
                return "無對賽記錄"
            
            # 格式化輸出： "主勝 3 - 和 1 - 客勝 2"
            return f"主贏{h_wins}場 | 和{draws}場 | 客贏{a_wins}場"
        else:
            return "N/A"
    except:
        return "N/A"

# ================= 核心邏輯 (整合 H2H) =================
def get_real_data():
    standings = get_all_standings()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 正在啟動抓取...")
    
    headers = {'X-Auth-Token': API_KEY}
    today = datetime.now()
    start_date = (today - timedelta(days=6)).strftime('%Y-%m-%d')
    end_date = (today + timedelta(days=3)).strftime('%Y-%m-%d')
    
    comp_str = ",".join(COMPETITIONS)
    params = {
        'dateFrom': start_date,
        'dateTo': end_date,
        'competitions': comp_str
    }

    try:
        response = requests.get(f"{BASE_URL}/matches", headers=headers, params=params)
        if response.status_code != 200:
            print(f"❌ API 請求失敗: {response.text}")
            return []

        data = response.json()
        matches = data.get('matches', [])
        
        if not matches:
            print(f"⚠️ 無比賽數據。")
            return []

        cleaned_data = []
        hk_tz = pytz.timezone('Asia/Hong_Kong')

        print(f"🔍 找到 {len(matches)} 場比賽，準備逐一處理 (這可能需要幾分鐘)...")

        for index, match in enumerate(matches):
            # 時間
            utc_str = match['utcDate']
            utc_dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
            hk_dt = utc_dt.astimezone(hk_tz)
            time_str = hk_dt.strftime('%Y-%m-%d %H:%M') 

            # 狀態
            status_raw = match['status']
            status = '未開賽'
            if status_raw in ['IN_PLAY', 'PAUSED']: status = '進行中'
            elif status_raw == 'FINISHED': status = '完場'
            
            score_h = match['score']['fullTime']['home']
            score_a = match['score']['fullTime']['away']

            # 匹配排名
            home_id = match['homeTeam']['id']
            away_id = match['awayTeam']['id']
            home_info = standings.get(home_id, {'rank': '-', 'form': 'N/A'})
            away_info = standings.get(away_id, {'rank': '-', 'form': 'N/A'})

            # --- H2H 處理邏輯 (關鍵修改) ---
            # 只有當比賽「未開賽」或「進行中」時才去查 API，節省次數
            h2h_str = "完場不顯示"
            if status != '完場':
                print(f"   ⏳ [{index+1}/{len(matches)}] 正在查 H2H: {match['homeTeam']['name']} vs {match['awayTeam']['name']} ...")
                h2h_str = get_h2h_data(match['id'])
                # 【重要】每查一次停 6.5 秒，確保不超過每分鐘 10 次的限制
                time.sleep(6.5)
            else:
                # 已完場的比賽直接略過 H2H 查詢，加快速度
                h2h_str = "N/A"

            # 模擬預測
            h_rank_val = home_info['rank'] if isinstance(home_info['rank'], int) else 10
            a_rank_val = away_info['rank'] if isinstance(away_info['rank'], int) else 10
            rank_bias_h = (20 - h_rank_val) * 0.02
            rank_bias_a = (20 - a_rank_val) * 0.02
            fake_home_exp = round(random.uniform(0.8, 2.5) + rank_bias_h, 2)
            fake_away_exp = round(random.uniform(0.6, 2.0) + rank_bias_a, 2)

            match_info = {
                '時間': time_str,
                '聯賽': match['competition']['name'],
                '主隊': match['homeTeam']['shortName'] or match['homeTeam']['name'],
                '客隊': match['awayTeam']['shortName'] or match['awayTeam']['name'],
                '主排名': home_info['rank'], 
                '客排名': away_info['rank'],
                '主近況': home_info['form'],
                '客近況': away_info['form'],
                '主預測': fake_home_exp,
                '客預測': fake_away_exp,
                '總球數': round(fake_home_exp + fake_away_exp, 1),
                '主攻(H)': round(fake_home_exp * 1.2, 1),
                '客攻(A)': round(fake_away_exp * 1.1, 1),
                '狀態': status,
                '主分': score_h if score_h is not None else '',
                '客分': score_a if score_a is not None else '',
                'H2H': h2h_str # 寫入真實 H2H
            }
            cleaned_data.append(match_info)
            
        print(f"✅ 成功處理 {len(cleaned_data)} 場賽事！")
        return cleaned_data
    except Exception as e:
        print(f"⚠️ 執行錯誤: {e}")
        return []

# ================= 主程式 =================
def main():
    real_data = get_real_data()
    
    if real_data:
        df = pd.DataFrame(real_data)
        cols = ['時間', '聯賽', '主隊', '客隊', '主排名', '客排名', '主近況', '客近況', 
                '主預測', '客預測', '總球數', '主攻(H)', '客攻(A)', '狀態', '主分', '客分', 'H2H']
        df = df.reindex(columns=cols, fill_value='')
        
        sheet = connect_google_sheet()
        if sheet:
            try:
                print(f"🚀 正在更新 Google Sheet...")
                header = df.columns.values.tolist()
                values = df.astype(str).values.tolist()
                data_to_upload = [header] + values
                
                sheet.clear()
                sheet.update(range_name='A1', values=data_to_upload)
                print(f"☁️ Google Sheet 更新成功！")
            except Exception as e:
                print(f"❌ 上傳失敗: {e}")
    else:
        print("⚠️ 無數據可更新。")

if __name__ == "__main__":
    main()
