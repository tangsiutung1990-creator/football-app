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
        # 如果額度低於 50，強制停止以防爆額
        if remaining and int(remaining) < 50:
            print(f"⚠️ API 額度過低 (剩餘 {remaining})，停止運行。")
            return "STOP"
        if response.status_code == 200: return response.json()
    except Exception as e:
        print(f"API Error: {e}")
    return None

# ================= Google Sheet 工具 =================
def get_google_spreadsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if os.path.exists("key.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        elif "GCP_SERVICE_ACCOUNT" in os.environ:
             creds_dict = eval(os.environ["GCP_SERVICE_ACCOUNT"])
             creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            return None
        client = gspread.authorize(creds)
        return client.open(GOOGLE_SHEET_NAME)
    except: return None

# ================= 數據獲取 =================
def get_league_standings(league_id, season):
    data = call_api('standings', {'league': league_id, 'season': season})
    if data == "STOP": return "STOP"
    standings_map = {}
    if not data or not data.get('response'): return standings_map
    try:
        for group in data['response'][0]['league']['standings']:
            for team in group:
                standings_map[team['team']['id']] = {'rank': team['rank'], 'form': team['form']}
    except: pass
    return standings_map

def get_best_odds(fixture_id):
    data = call_api('odds', {'fixture': fixture_id})
    if data == "STOP": return "STOP", 0, 0
    if not data or not data.get('response'): return 0, 0, 0
    try:
        bks = data['response'][0]['bookmakers']
        target = next((b for b in bks if b['id'] in [1, 6, 8, 2]), bks[0] if bks else None)
        if target:
            bet = next((b for b in target['bets'] if b['name'] == 'Match Winner'), None)
            if bet:
                vals = {o['value']: float(o['odd']) for o in bet['values']}
                return vals.get('Home', 0), vals.get('Draw', 0), vals.get('Away', 0)
    except: pass
    return 0, 0, 0

# ================= 數學計算 =================
def poisson_prob(k, lam):
    return (math.pow(lam, k) * math.exp(-lam)) / math.factorial(k) if lam > 0 else 0

def calculate_probs(h_rank, a_rank):
    # 簡易 xG 模擬 (基於排名)
    base = 1.35
    h_xg = max(0.5, min(3.0, base + (a_rank - h_rank) * 0.05))
    a_xg = max(0.5, min(3.0, base + (h_rank - a_rank) * 0.05))
    
    h_win, a_win, o25, btts = 0, 0, 0, 0
    for h in range(6):
        for a in range(6):
            p = poisson_prob(h, h_xg) * poisson_prob(a, a_xg)
            if h > a: h_win += p
            if a > h: a_win += p
            if h+a > 2.5: o25 += p
            if h>0 and a>0: btts += p
            
    return h_xg, a_xg, h_win*100, a_win*100, o25*100, btts*100

# ================= 主程式 =================
def main():
    print("🚀 V38.1 Smart-Eco 啟動...")
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    
    # 掃描前後 1 天 (共 3 天)
    utc_now = datetime.now(pytz.utc)
    from_date = (utc_now - timedelta(days=1)).strftime('%Y-%m-%d')
    to_date = (utc_now + timedelta(days=1)).strftime('%Y-%m-%d')
    season = 2024 
    
    all_data = []

    for lg_id, lg_name in LEAGUE_ID_MAP.items():
        print(f"Checking {lg_name}...")
        standings = get_league_standings(lg_id, season)
        if standings == "STOP": break
        
        fixtures_data = call_api('fixtures', {'league': lg_id, 'season': season, 'from': from_date, 'to': to_date})
        if fixtures_data == "STOP": break
        if not fixtures_data or not fixtures_data.get('response'): continue
        
        for item in fixtures_data['response']:
            fix_id = item['fixture']['id']
            status = item['fixture']['status']['short']
            t_str = datetime.fromtimestamp(item['fixture']['timestamp'], pytz.utc).astimezone(hk_tz).strftime('%Y-%m-%d %H:%M')
            
            # 只有未開賽/進行中才查賠率
            odds_h, odds_d, odds_a = 0,0,0
            if status in ['NS', '1H', '2H', 'HT', 'LIVE']:
                res = get_best_odds(fix_id)
                if res == "STOP": break
                odds_h, odds_d, odds_a = res

            h_id = item['teams']['home']['id']
            a_id = item['teams']['away']['id']
            h_info = standings.get(h_id, {'rank': 10, 'form': ''})
            a_info = standings.get(a_id, {'rank': 10, 'form': ''})
            
            h_xg, a_xg, ph, pa, po, pb = calculate_probs(h_info['rank'], a_info['rank'])
            
            # Value Bet 判斷
            val_h = "💰" if odds_h > 0 and (ph/100 > 1/odds_h) else ""
            val_a = "💰" if odds_a > 0 and (pa/100 > 1/odds_a) else ""
            
            all_data.append({
                '時間': t_str, '聯賽': lg_name, '狀態': status,
                '主隊': item['teams']['home']['name'], '客隊': item['teams']['away']['name'],
                '主分': item['goals']['home'] if item['goals']['home'] is not None else "",
                '客分': item['goals']['away'] if item['goals']['away'] is not None else "",
                '主排名': h_info['rank'], '客排名': a_info['rank'],
                '主走勢': h_info['form'], '客走勢': a_info['form'],
                'xG主': round(h_xg, 2), 'xG客': round(a_xg, 2),
                '主胜率': int(ph), '客胜率': int(pa), '大2.5': int(po), 'BTTS': int(pb),
                '主賠': odds_h, '客賠': odds_a,
                '主Value': val_h, '客Value': val_a
            })
            time.sleep(0.1)

    # 確保無論有無數據，都生成一個帶有正確表頭的 DataFrame
    if all_data:
        df = pd.DataFrame(all_data)
    else:
        # 創建空 DataFrame 但包含所有欄位，防止 app.py 報錯
        cols = ['時間','聯賽','狀態','主隊','客隊','主分','客分','主排名','客排名',
                '主走勢','客走勢','xG主','xG客','主胜率','客胜率','大2.5','BTTS',
                '主賠','客賠','主Value','客Value']
        df = pd.DataFrame(columns=cols)

    # 保存與上傳
    df.to_csv(CSV_FILENAME, index=False, encoding='utf-8-sig')
    print("Backup saved.")
    
    sheet = get_google_spreadsheet()
    if sheet:
        try:
            sheet.sheet1.clear()
            # 將 NaN 轉為空字串再上傳
            df_str = df.fillna('').astype(str)
            # 確保第一行是標題
            payload = [df_str.columns.values.tolist()] + df_str.values.tolist()
            sheet.sheet1.update(range_name='A1', values=payload)
            print("✅ Uploaded to Google Sheet")
        except Exception as e:
            print(f"❌ Upload failed: {e}")

if __name__ == "__main__":
    main()
