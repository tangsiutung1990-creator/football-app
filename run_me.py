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
MANUAL_TAB_NAME = "球隊身價表" # 新分頁名稱
COMPETITIONS = ['PL', 'PD', 'CL', 'SA', 'BL1', 'FL1'] 

# ================= 連接 Google Sheet (升級版) =================
def get_google_spreadsheet():
    """
    回傳整個試算表物件 (Spreadsheet)，讓我們可以選擇不同分頁。
    """
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open(GOOGLE_SHEET_NAME)
        return spreadsheet
    except Exception as e:
        print(f"❌ Google Sheet 連線失敗: {e}")
        return None

# ================= 讀取「球隊身價表」分頁 =================
def load_manual_market_values(spreadsheet):
    """
    從 '球隊身價表' 分頁讀取數據，轉為字典對照表。
    格式: {'Man City': '1260', 'Liverpool': '800', ...}
    """
    print(f"📖 正在讀取 '{MANUAL_TAB_NAME}' 分頁...")
    market_value_map = {}
    
    try:
        # 嘗試打開該分頁
        worksheet = spreadsheet.worksheet(MANUAL_TAB_NAME)
        records = worksheet.get_all_records() # 讀取所有資料
        
        for row in records:
            # 假設欄位名稱是 "球隊名稱" 和 "身價"
            team_name = str(row.get('球隊名稱', '')).strip()
            value = str(row.get('身價', '')).strip()
            
            if team_name and value:
                market_value_map[team_name] = value
                
        print(f"✅ 成功讀取 {len(market_value_map)} 支球隊的身價資料！")
        return market_value_map

    except gspread.WorksheetNotFound:
        print(f"⚠️ 找不到分頁 '{MANUAL_TAB_NAME}'！請確認你已建立此分頁。")
        print("💡 程式將暫時使用 'N/A'，請盡快建立分頁。")
        return {}
    except Exception as e:
        print(f"⚠️ 讀取身價表時發生錯誤: {e}")
        return {}

# ================= 獲取聯賽排名 =================
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

# ================= H2H + 大小球統計 (近10場) =================
def get_h2h_and_ou_stats(match_id, current_home_id, current_away_id):
    headers = {'X-Auth-Token': API_KEY}
    url = f"{BASE_URL}/matches/{match_id}/head2head"
    
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            matches = data.get('matches', []) 
            
            if not matches:
                return "無對賽記錄", "N/A"
            
            matches.sort(key=lambda x: x['utcDate'], reverse=True)
            recent_matches = matches[:10]
            total_games = 0
            
            h_wins = 0
            a_wins = 0
            draws = 0
            o15 = 0
            o25 = 0
            o35 = 0
            
            for m in recent_matches:
                if m['status'] != 'FINISHED':
                    continue
                total_games += 1
                
                winner = m['score']['winner']
                if winner == 'DRAW': draws += 1
                elif winner == 'HOME_TEAM':
                    if m['homeTeam']['id'] == current_home_id: h_wins += 1
                    else: a_wins += 1
                elif winner == 'AWAY_TEAM':
                    if m['awayTeam']['id'] == current_home_id: h_wins += 1
                    else: a_wins += 1
                
                try:
                    goals = m['score']['fullTime']['home'] + m['score']['fullTime']['away']
                    if goals > 1.5: o15 += 1
                    if goals > 2.5: o25 += 1
                    if goals > 3.5: o35 += 1
                except: pass 
            
            if total_games == 0: return "無有效對賽", "N/A"

            p15 = round((o15 / total_games) * 100)
            p25 = round((o25 / total_games) * 100)
            p35 = round((o35 / total_games) * 100)

            h2h_str = f"近{total_games}場: 主{h_wins}勝 | 和{draws} | 客{a_wins}勝"
            ou_str = f"近{total_games}場大球率: 1.5球({p15}%) | 2.5球({p25}%) | 3.5球({p35}%)"
            return h2h_str, ou_str
        else:
            return "N/A", "N/A"
    except Exception as e:
        print(f"H2H Error: {e}")
        return "N/A", "N/A"

# ================= 核心邏輯 (接收 market_value_map) =================
def get_real_data(market_value_map):
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

        print(f"🔍 找到 {len(matches)} 場比賽，準備逐一處理...")
        
        # 用來提示用戶哪些球隊名稱還沒填
        missing_teams = set()

        for index, match in enumerate(matches):
            utc_str = match['utcDate']
            utc_dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
            hk_dt = utc_dt.astimezone(hk_tz)
            time_str = hk_dt.strftime('%Y-%m-%d %H:%M') 

            status_raw = match['status']
            status = '未開賽'
            if status_raw in ['IN_PLAY', 'PAUSED']: status = '進行中'
            elif status_raw == 'FINISHED': status = '完場'
            
            score_h = match['score']['fullTime']['home']
            score_a = match['score']['fullTime']['away']

            home_id = match['homeTeam']['id']
            away_id = match['awayTeam']['id']
            
            # --- 獲取球隊名稱 (關鍵) ---
            home_name = match['homeTeam']['shortName'] or match['homeTeam']['name']
            away_name = match['awayTeam']['shortName'] or match['awayTeam']['name']
            
            home_info = standings.get(home_id, {'rank': '-', 'form': 'N/A'})
            away_info = standings.get(away_id, {'rank': '-', 'form': 'N/A'})

            # --- 身價配對 (從字典讀取) ---
            # 如果找不到，回傳 "N/A" (或者你可以填 "請填寫")
            home_value = market_value_map.get(home_name, "N/A")
            away_value = market_value_map.get(away_name, "N/A")
            
            if home_value == "N/A": missing_teams.add(home_name)
            if away_value == "N/A": missing_teams.add(away_name)

            # --- H2H 與 大小球 ---
            h2h_str = "完場不顯示"
            ou_stats_str = "N/A"
            
            if status != '完場':
                print(f"   ⏳ [{index+1}/{len(matches)}] 正在查數據: {home_name} vs {away_name} ...")
                h2h_str, ou_stats_str = get_h2h_and_ou_stats(match['id'], home_id, away_id)
                time.sleep(6.5) 
            else:
                h2h_str = "N/A"
                ou_stats_str = "N/A"

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
                '主隊': home_name,
                '客隊': away_name,
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
                'H2H': h2h_str,
                '大小球統計': ou_stats_str,
                '主隊身價': home_value, 
                '客隊身價': away_value
            }
            cleaned_data.append(match_info)
            
        print(f"✅ 成功處理 {len(cleaned_data)} 場賽事！")
        
        # 溫馨提示：印出還沒填身價的球隊
        if missing_teams:
            print("\n⚠️ 以下球隊在 '球隊身價表' 找不到資料 (建議去填寫):")
            print(", ".join(list(missing_teams)[:10]) + "...")
            
        return cleaned_data
    except Exception as e:
        print(f"⚠️ 執行錯誤: {e}")
        return []

# ================= 主程式 =================
def main():
    # 1. 獲取 Spreadsheet 物件
    spreadsheet = get_google_spreadsheet()
    
    market_value_map = {}
    if spreadsheet:
        # 2. 從分頁 2 (球隊身價表) 讀取對照表
        market_value_map = load_manual_market_values(spreadsheet)
    
    # 3. 抓取新數據 (傳入對照表)
    real_data = get_real_data(market_value_map)
    
    if real_data:
        df = pd.DataFrame(real_data)
        cols = ['時間', '聯賽', '主隊', '客隊', '主排名', '客排名', '主近況', '客近況', 
                '主預測', '客預測', '總球數', '主攻(H)', '客攻(A)', '狀態', '主分', '客分', 'H2H', '大小球統計', '主隊身價', '客隊身價']
        df = df.reindex(columns=cols, fill_value='')
        
        if spreadsheet:
            try:
                print(f"🚀 正在更新 '{GOOGLE_SHEET_NAME}' 分頁...")
                # 寫入分頁 1 (數據上傳)
                upload_sheet = spreadsheet.sheet1 
                
                header = df.columns.values.tolist()
                values = df.astype(str).values.tolist()
                data_to_upload = [header] + values
                
                upload_sheet.clear()
                upload_sheet.update(range_name='A1', values=data_to_upload)
                print(f"☁️ Google Sheet 更新成功！")
            except Exception as e:
                print(f"❌ 上傳失敗: {e}")
    else:
        print("⚠️ 無數據可更新。")

if __name__ == "__main__":
    main()
