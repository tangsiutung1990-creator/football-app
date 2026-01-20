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

# 核心聯賽名單
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
        # 保護機制：額度低於 30 停止
        if remaining and int(remaining) < 30:
            print(f"⚠️ API 額度過低 (剩餘 {remaining})，停止運行。")
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

# ================= 詳細賠率抓取 (核心功能) =================
def get_detailed_odds(fixture_id):
    # 這裡會消耗 API Call，用來抓取 ID 1(獨贏), 4(亞盤), 5(大小)
    data = call_api('odds', {'fixture': fixture_id})
    if data == "STOP": return "STOP", {}
    
    odds_data = {
        'home_win': 0, 'draw': 0, 'away_win': 0,
        'ah_line': '', 'ah_home': 0, 'ah_away': 0,
        'ou_line': '', 'ou_over': 0, 'ou_under': 0
    }
    
    if not data or not data.get('response'): return "OK", odds_data
    
    try:
        # 優先找主流博彩公司 (Bet365=1, 1xBet=6)
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
                
                # ID 5: 大小球 (Goals Over/Under)
                elif bet['id'] == 5:
                    # 嘗試抓 2.5，如果沒有就抓第一個
                    target_val = next((v for v in bet['values'] if v['value'] == 'Over 2.5'), None)
                    if target_val:
                        odds_data['ou_line'] = "2.5"
                        for v in bet['values']:
                            if 'Over' in v['value']: odds_data['ou_over'] = float(v['odd'])
                            if 'Under' in v['value']: odds_data['ou_under'] = float(v['odd'])
                    elif len(bet['values']) > 0:
                        raw = bet['values'][0]['value'] # e.g. "Over 3.5"
                        odds_data['ou_line'] = raw.replace('Over ','').replace('Under ','')
                        for v in bet['values']:
                            if 'Over' in v['value']: odds_data['ou_over'] = float(v['odd'])
                            if 'Under' in v['value']: odds_data['ou_under'] = float(v['odd'])

                # ID 4: 亞洲讓球 (Asian Handicap)
                elif bet['id'] == 4:
                    if len(bet['values']) > 0:
                        # 這裡的 value 通常是 Home/Away，盤口可能在 extra 或 label
                        # 簡單處理：存下賠率
                        for v in bet['values']:
                            if v['value'] == 'Home': odds_data['ah_home'] = float(v['odd'])
                            if v['value'] == 'Away': odds_data['ah_away'] = float(v['odd'])
    except: pass
    return "OK", odds_data

# ================= 主程式 =================
def main():
    print("🚀 V39.0 Update Started (Full Features)")
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    
    # 時間範圍：昨天 + 今天 + 明天 (3天範圍)
    utc_now = datetime.now(pytz.utc)
    from_date = (utc_now - timedelta(days=1)).strftime('%Y-%m-%d')
    to_date = (utc_now + timedelta(days=1)).strftime('%Y-%m-%d')
    season = 2024
    
    all_data = []

    for lg_id, lg_name in LEAGUE_ID_MAP.items():
        print(f"Checking {lg_name}...")
        
        fixtures_data = call_api('fixtures', {'league': lg_id, 'season': season, 'from': from_date, 'to': to_date})
        if fixtures_data == "STOP": break
        if not fixtures_data or not fixtures_data.get('response'): continue
        
        for item in fixtures_data['response']:
            fix_id = item['fixture']['id']
            status = item['fixture']['status']['short']
            t_str = datetime.fromtimestamp(item['fixture']['timestamp'], pytz.utc).astimezone(hk_tz).strftime('%Y-%m-%d %H:%M')
            
            # 狀態翻譯
            if status in ['FT', 'AET', 'PEN']: status_txt = "完場"
            elif status in ['NS']: status_txt = "未開賽"
            elif status in ['1H', 'HT', '2H', 'ET', 'LIVE']: status_txt = "進行中"
            elif status in ['PST', 'CANC', 'ABD']: status_txt = "取消/延遲"
            else: status_txt = status

            # 只有未開賽或進行中才抓賠率 (省流)，或者你可以全抓
            # 這裡設定為：如果不是取消的比賽都抓
            odds = {}
            if "取消" not in status_txt:
                res_code, odds = get_detailed_odds(fix_id)
                if res_code == "STOP": break
            
            # 構建數據行
            all_data.append({
                '時間': t_str, '聯賽': lg_name, '狀態': status_txt,
                '主隊': item['teams']['home']['name'], '客隊': item['teams']['away']['name'],
                '主分': item['goals']['home'] if item['goals']['home'] is not None else "",
                '客分': item['goals']['away'] if item['goals']['away'] is not None else "",
                
                # 賠率數據
                '主勝': odds.get('home_win', 0), 
                '和局': odds.get('draw', 0), 
                '客勝': odds.get('away_win', 0),
                '亞盤主': odds.get('ah_home', 0),
                '亞盤客': odds.get('ah_away', 0),
                '球頭': odds.get('ou_line', ''),
                '大球': odds.get('ou_over', 0),
                '小球': odds.get('ou_under', 0)
            })
            time.sleep(0.1) # 避免過快

    # 保存數據
    cols = ['時間','聯賽','狀態','主隊','客隊','主分','客分',
            '主勝','和局','客勝','亞盤主','亞盤客','球頭','大球','小球']
            
    if all_data:
        df = pd.DataFrame(all_data)
    else:
        df = pd.DataFrame(columns=cols)

    # 1. 保存 CSV
    df.to_csv(CSV_FILENAME, index=False, encoding='utf-8-sig')
    print(f"Backup saved: {len(df)} rows.")
    
    # 2. 上傳 Google Sheet
    sheet = get_google_spreadsheet()
    if sheet:
        try:
            sheet.sheet1.clear()
            # 轉成字串避免 JSON 錯誤
            df_str = df.fillna('').astype(str)
            payload = [df_str.columns.values.tolist()] + df_str.values.tolist()
            sheet.sheet1.update(range_name='A1', values=payload)
            print("✅ Uploaded to Google Sheet")
        except Exception as e: print(f"❌ Upload failed: {e}")

if __name__ == "__main__":
    main()
