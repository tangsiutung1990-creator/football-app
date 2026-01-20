import requests
import pandas as pd
import time
import gspread
from datetime import datetime, timedelta
import pytz
from oauth2client.service_account import ServiceAccountCredentials
import os
import math

# ================= 設定區 =================
API_KEY = '6bf59594223b07234f75a8e2e2de5178' 
BASE_URL = 'https://v3.football.api-sports.io'
GOOGLE_SHEET_NAME = "數據上傳" 
CSV_FILENAME = "football_data_backup.csv" 

# 主要聯賽 ID (可根據需要增減)
LEAGUE_ID_MAP = {
    39: '英超', 40: '英冠', 140: '西甲', 135: '意甲', 78: '德甲', 61: '法甲', 
    88: '荷甲', 94: '葡超', 179: '蘇超', 98: '日職', 292: '韓K1', 
    188: '澳職', 253: '美職', 2: '歐聯', 3: '歐霸'
}

# ================= API 工具 =================
def call_api(endpoint, params=None):
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-apisports-key': API_KEY}
    url = f"{BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        remaining = response.headers.get('x-ratelimit-requests-remaining')
        if remaining and int(remaining) < 30:
            print(f"⚠️ API 額度極低 (剩餘 {remaining})，停止運行。")
            return "STOP"
        if response.status_code == 200: return response.json()
    except Exception as e:
        print(f"API Error: {e}")
    return None

# ================= Google Sheet =================
def get_google_spreadsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if os.path.exists("key.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        elif "GCP_SERVICE_ACCOUNT" in os.environ:
             creds_dict = eval(os.environ["GCP_SERVICE_ACCOUNT"])
             creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else: return None
        client = gspread.authorize(creds)
        return client.open(GOOGLE_SHEET_NAME)
    except: return None

# ================= 詳細賠率獲取 (核心修改) =================
def get_detailed_odds(fixture_id):
    # 這是為了獲取 1x2, 亞盤, 大小球
    data = call_api('odds', {'fixture': fixture_id})
    if data == "STOP": return "STOP", {}
    if not data or not data.get('response'): return "OK", {}
    
    odds_data = {
        'home_win': 0, 'draw': 0, 'away_win': 0,
        'ah_line': '', 'ah_home': 0, 'ah_away': 0, # 亞盤
        'ou_line': '', 'ou_over': 0, 'ou_under': 0 # 大小
    }
    
    try:
        # 優先找 Bet365 (id: 1) 或 1xBet (id: 6)
        bks = data['response'][0]['bookmakers']
        target_bk = next((b for b in bks if b['id'] in [1, 6, 8]), bks[0] if bks else None)
        
        if target_bk:
            for bet in target_bk['bets']:
                # ID 1: 獨贏 (Match Winner)
                if bet['id'] == 1:
                    for val in bet['values']:
                        if val['value'] == 'Home': odds_data['home_win'] = float(val['odd'])
                        if val['value'] == 'Draw': odds_data['draw'] = float(val['odd'])
                        if val['value'] == 'Away': odds_data['away_win'] = float(val['odd'])
                
                # ID 5: 大小球 (Goals Over/Under) - 找最接近 2.5 的
                elif bet['id'] == 5:
                    # 簡單邏輯：取第一個盤口，通常是均衡盤
                    # 或者刻意找 2.5
                    target_val = next((v for v in bet['values'] if v['value'] == 'Over 2.5'), None)
                    if target_val:
                        # 這是 2.5 盤
                        odds_data['ou_line'] = "2.5"
                        for v in bet['values']:
                            if 'Over' in v['value']: odds_data['ou_over'] = float(v['odd'])
                            if 'Under' in v['value']: odds_data['ou_under'] = float(v['odd'])
                    elif len(bet['values']) > 0:
                        # 拿預設的第一個盤
                        raw_val = bet['values'][0]['value'] # e.g., "Over 3.5"
                        line = raw_val.replace('Over ','').replace('Under ','')
                        odds_data['ou_line'] = line
                        for v in bet['values']:
                            if 'Over' in v['value']: odds_data['ou_over'] = float(v['odd'])
                            if 'Under' in v['value']: odds_data['ou_under'] = float(v['odd'])

                # ID 4: 亞洲讓球 (Asian Handicap)
                elif bet['id'] == 4:
                    # 取第一個均衡盤
                    if len(bet['values']) > 0:
                        odds_data['ah_line'] = bet['values'][0]['value'] # e.g. "Home +0.5" 的 value 其實在 API 裡是 label
                        # API Sports 的 AH 結構比較特殊，value 欄位通常是賠率，extra 可能是盤口
                        # 這裡簡化處理，直接取賠率
                        for v in bet['values']:
                            if v['value'] == 'Home': odds_data['ah_home'] = float(v['odd'])
                            if v['value'] == 'Away': odds_data['ah_away'] = float(v['odd'])
                        # 嘗試抓盤口 (有些 bookmaker 會寫在 extra)
                        # 如果 API 沒給明確盤口，我們只能顯示賠率
                        
    except Exception as e: pass
    return "OK", odds_data

# ================= 主程式 =================
def main():
    print("🚀 V39.0 全功能數據版 (含亞盤/大小)")
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    
    # 掃描前後 1 天 (保持省流，但數據深度增加)
    utc_now = datetime.now(pytz.utc)
    from_date = (utc_now - timedelta(days=1)).strftime('%Y-%m-%d')
    to_date = (utc_now + timedelta(days=1)).strftime('%Y-%m-%d')
    season = 2024
    
    all_data = []

    for lg_id, lg_name in LEAGUE_ID_MAP.items():
        print(f"Checking {lg_name}...")
        
        # 1. 獲取賽程
        fixtures_data = call_api('fixtures', {'league': lg_id, 'season': season, 'from': from_date, 'to': to_date})
        if fixtures_data == "STOP": break
        if not fixtures_data or not fixtures_data.get('response'): continue
        
        for item in fixtures_data['response']:
            fix_id = item['fixture']['id']
            status = item['fixture']['status']['short'] # NS, FT, 1H, PST, CAND
            t_str = datetime.fromtimestamp(item['fixture']['timestamp'], pytz.utc).astimezone(hk_tz).strftime('%Y-%m-%d %H:%M')
            
            # 狀態分類
            if status in ['FT', 'AET', 'PEN']: status_txt = "完場"
            elif status in ['NS']: status_txt = "未開賽"
            elif status in ['1H', 'HT', '2H', 'ET', 'P', 'LIVE']: status_txt = "進行中"
            elif status in ['PST', 'CANC', 'ABD']: status_txt = "取消/延遲"
            else: status_txt = status

            # 2. 獲取詳細賠率 (如果是完場，可以選擇不抓以省流，但為了完整性這裡還是抓)
            # 如果你只想看未開賽的盤口，可以在這裡加 if status_txt != "完場":
            res_code, odds = get_detailed_odds(fix_id)
            if res_code == "STOP": break

            # 3. 排名 (簡單獲取)
            # 這裡簡化，不 call standings API 節省額度，或者你可以保留之前的 standings call
            # 為了省流，這裡假設排名為空，或者你需要解除註解下方的 standings 邏輯
            # 如果你有額度，可以把之前的 get_league_standings 加回來
            h_rank = "?"
            a_rank = "?"

            all_data.append({
                '時間': t_str, '聯賽': lg_name, '狀態': status_txt,
                '主隊': item['teams']['home']['name'], '客隊': item['teams']['away']['name'],
                '主分': item['goals']['home'] if item['goals']['home'] is not None else "",
                '客分': item['goals']['away'] if item['goals']['away'] is not None else "",
                '主排名': h_rank, '客排名': a_rank,
                
                # 獨贏
                '主勝': odds.get('home_win', 0), 
                '和局': odds.get('draw', 0), 
                '客勝': odds.get('away_win', 0),
                
                # 亞盤 (Asian Handicap)
                '亞盤主': odds.get('ah_home', 0),
                '亞盤客': odds.get('ah_away', 0),
                
                # 大小球 (Over/Under)
                '球頭': odds.get('ou_line', ''),
                '大球': odds.get('ou_over', 0),
                '小球': odds.get('ou_under', 0),
                
                # xG (如果有)
                'xG主': 0, 'xG客': 0 # 需額外 Call Prediction，這裡先置空省額度
            })
            time.sleep(0.1)

    # 保存與上傳
    cols = ['時間','聯賽','狀態','主隊','客隊','主分','客分','主排名','客排名',
            '主勝','和局','客勝','亞盤主','亞盤客','球頭','大球','小球','xG主','xG客']
            
    if all_data:
        df = pd.DataFrame(all_data)
    else:
        df = pd.DataFrame(columns=cols)

    df.to_csv(CSV_FILENAME, index=False, encoding='utf-8-sig')
    print(f"Backup saved. Rows: {len(df)}")
    
    sheet = get_google_spreadsheet()
    if sheet:
        try:
            sheet.sheet1.clear()
            df_str = df.fillna('').astype(str)
            payload = [df_str.columns.values.tolist()] + df_str.values.tolist()
            sheet.sheet1.update(range_name='A1', values=payload)
            print("✅ Uploaded to Google Sheet")
        except Exception as e: print(f"❌ Upload failed: {e}")

if __name__ == "__main__":
    main()
