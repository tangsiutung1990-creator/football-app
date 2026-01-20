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

# 只保留主要聯賽以節省 API (可根據需求增減)
LEAGUE_ID_MAP = {
    39: '英超', 40: '英冠', 140: '西甲', 135: '意甲', 78: '德甲', 61: '法甲', 
    88: '荷甲', 94: '葡超', 179: '蘇超', 98: '日職', 292: '韓K1', 
    188: '澳職', 253: '美職', 2: '歐聯', 3: '歐霸'
}

# ================= API 連接 (含額度保護) =================
def call_api(endpoint, params=None):
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-apisports-key': API_KEY}
    url = f"{BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        # 檢查剩餘額度
        remaining = response.headers.get('x-ratelimit-requests-remaining')
        if remaining and int(remaining) < 50:
            print(f"⚠️ API 額度過低 (剩餘 {remaining})，強制停止以防爆額。")
            return "STOP"

        if response.status_code == 200: return response.json()
        return None
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
        else:
            return None
        client = gspread.authorize(creds)
        return client.open(GOOGLE_SHEET_NAME)
    except Exception as e: 
        print(f"Sheet Error: {e}")
        return None

# ================= 數據工具 =================
def get_league_standings(league_id, season):
    data = call_api('standings', {'league': league_id, 'season': season})
    if data == "STOP": return "STOP"
    standings_map = {}
    if not data or not data.get('response'): return standings_map
    try:
        standings_response = data['response'][0]['league']['standings']
        for group in standings_response:
            for team in group:
                t_id = team['team']['id']
                standings_map[t_id] = {'rank': team['rank'], 'form': team['form']}
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
                h=0; d=0; a=0
                for o in bet['values']:
                    if o['value'] == 'Home': h = float(o['odd'])
                    if o['value'] == 'Draw': d = float(o['odd'])
                    if o['value'] == 'Away': a = float(o['odd'])
                return h, d, a
    except: pass
    return 0, 0, 0

# ================= 數學模型 =================
def poisson_prob(k, lam):
    return (math.pow(lam, k) * math.exp(-lam)) / math.factorial(k) if lam > 0 else 0

def calculate_probs(h_exp, a_exp):
    h_win = 0; a_win = 0; o25 = 0; btts = 0
    for h in range(8):
        for a in range(8):
            prob = poisson_prob(h, h_exp) * poisson_prob(a, a_exp)
            if h > a: h_win += prob
            if a > h: a_win += prob
            if h + a > 2.5: o25 += prob
            if h > 0 and a > 0: btts += prob
    return h_win*100, a_win*100, o25*100, btts*100

# ================= 主程式 =================
def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 V38.1 Smart-Eco 啟動")
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    
    # 設定為前後 1 天 (共 3 天)，大幅節省 API
    utc_now = datetime.now(pytz.utc)
    from_date = (utc_now - timedelta(days=1)).strftime('%Y-%m-%d')
    to_date = (utc_now + timedelta(days=1)).strftime('%Y-%m-%d')
    season = 2024 # 或是 2025，視乎你的聯賽

    print(f"📅 掃描範圍: {from_date} 至 {to_date}")
    
    all_data = []

    for lg_id, lg_name in LEAGUE_ID_MAP.items():
        print(f"   🔍 {lg_name}...")
        standings = get_league_standings(lg_id, season)
        if standings == "STOP": break
        
        fixtures_data = call_api('fixtures', {'league': lg_id, 'season': season, 'from': from_date, 'to': to_date})
        if fixtures_data == "STOP": break
        if not fixtures_data or not fixtures_data.get('response'): continue
        
        fixtures = fixtures_data['response']
        
        for item in fixtures:
            fix_id = item['fixture']['id']
            status = item['fixture']['status']['short']
            t_str = datetime.fromtimestamp(item['fixture']['timestamp'], pytz.utc).astimezone(hk_tz).strftime('%Y-%m-%d %H:%M')
            
            # 只有未開賽或進行中才 Call 賠率，完場比賽跳過賠率查詢以省流
            is_live_or_ns = status in ['NS', '1H', '2H', 'HT', 'LIVE']
            
            odds_h, odds_d, odds_a = 0,0,0
            if is_live_or_ns:
                res_odds = get_best_odds(fix_id)
                if res_odds == "STOP": break
                odds_h, odds_d, odds_a = res_odds

            # 簡化版 xG 計算 (模擬)
            # 為了省流，這裡不 Call Predictions API，改用排名估算
            h_id = item['teams']['home']['id']
            a_id = item['teams']['away']['id']
            h_rank = standings.get(h_id, {}).get('rank', 10)
            a_rank = standings.get(a_id, {}).get('rank', 10)
            
            # 簡單算法：排名越高(數字越小)進球期望越高
            base_xg = 1.35
            h_xg = base_xg + (a_rank - h_rank) * 0.05
            a_xg = base_xg + (h_rank - a_rank) * 0.05
            h_xg = max(0.5, min(3.0, h_xg))
            a_xg = max(0.5, min(3.0, a_xg))
            
            ph, pa, po, pb = calculate_probs(h_xg, a_xg)
            
            # Value 計算
            val_h = "💰" if odds_h > 0 and (ph/100 > 1/odds_h) else ""
            val_a = "💰" if odds_a > 0 and (pa/100 > 1/odds_a) else ""
            
            all_data.append({
                '時間': t_str, '聯賽': lg_name, 
                '主隊': item['teams']['home']['name'], '客隊': item['teams']['away']['name'],
                '狀態': status,
                '主分': item['goals']['home'] if item['goals']['home'] is not None else "",
                '客分': item['goals']['away'] if item['goals']['away'] is not None else "",
                '主排名': h_rank, '客排名': a_rank,
                '主走勢': standings.get(h_id, {}).get('form', ''),
                '客走勢': standings.get(a_id, {}).get('form', ''),
                'xG主': round(h_xg, 2), 'xG客': round(a_xg, 2),
                '主胜率': int(ph), '客胜率': int(pa), '大2.5': int(po), 'BTTS': int(pb),
                '主賠': odds_h, '客賠': odds_a,
                '主Value': val_h, '客Value': val_a
            })
            time.sleep(0.1) # 輕微延遲避免 Rate Limit

    if all_data:
        df = pd.DataFrame(all_data)
        df.to_csv(CSV_FILENAME, index=False, encoding='utf-8-sig')
        print(f"💾 已保存 {len(df)} 場比賽數據")
        
        sheet = get_google_spreadsheet()
        if sheet:
            try:
                sheet.sheet1.clear()
                df_str = df.fillna('').astype(str)
                sheet.sheet1.update([df_str.columns.values.tolist()] + df_str.values.tolist())
                print("✅ Google Sheet 上傳成功")
            except Exception as e: print(f"❌ 上傳失敗: {e}")
    else:
        print("⚠️ 無數據或額度耗盡")

if __name__ == "__main__":
    main()
