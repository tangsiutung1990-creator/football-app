import requests
import pandas as pd
import math
import time
import gspread
from datetime import datetime, timedelta
import pytz
from oauth2client.service_account import ServiceAccountCredentials
import os
import sys

# ================= 設定區 =================
API_KEY = '6bf59594223b07234f75a8e2e2de5178' 
BASE_URL = 'https://v3.football.api-sports.io'
GOOGLE_SHEET_NAME = "數據上傳" 

# HKJC 常見聯賽 ID 對照表
LEAGUE_ID_MAP = {
    39: '英超', 40: '英冠', 41: '英甲', 140: '西甲', 141: '西乙',
    135: '意甲', 78: '德甲', 61: '法甲', 88: '荷甲', 94: '葡超',
    144: '比甲', 179: '蘇超', 203: '土超', 119: '丹超', 113: '瑞典超',
    103: '挪超', 98: '日職', 292: '韓K1', 188: '澳職', 253: '美職',
    262: '墨超', 71: '巴甲', 128: '阿甲', 265: '智甲',
    2: '歐聯', 3: '歐霸'
}

# ================= API 連接 =================
def call_api(endpoint, params=None):
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-apisports-key': API_KEY}
    url = f"{BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200: return response.json()
        return None
    except: return None

# ================= Google Sheet (帶防錯) =================
def get_google_spreadsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if os.path.exists("key.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
            client = gspread.authorize(creds)
            return client.open(GOOGLE_SHEET_NAME)
        else:
            return None
    except Exception as e:
        return None

# ================= 數據獲取工具 =================
def get_league_standings(league_id, season):
    data = call_api('standings', {'league': league_id, 'season': season})
    standings_map = {}
    if not data or not data.get('response'): return standings_map
    try:
        standings_response = data['response'][0]['league']['standings']
        all_teams = []
        for group in standings_response: all_teams.extend(group)
        for team in all_teams:
            t_id = team['team']['id']
            h_played = team['home']['played']; h_for = team['home']['goals']['for']; h_ag = team['home']['goals']['against']
            a_played = team['away']['played']; a_for = team['away']['goals']['for']; a_ag = team['away']['goals']['against']
            standings_map[t_id] = {
                'rank': team['rank'], 'form': team['form'],
                'home_stats': {'played': h_played, 'avg_goals_for': h_for/h_played if h_played>0 else 0, 'avg_goals_against': h_ag/h_played if h_played>0 else 0},
                'away_stats': {'played': a_played, 'avg_goals_for': a_for/a_played if a_played>0 else 0, 'avg_goals_against': a_ag/a_played if a_played>0 else 0}
            }
    except: pass
    return standings_map

def get_h2h_stats(h_id, a_id):
    data = call_api('fixtures/headtohead', {'h2h': f"{h_id}-{a_id}"})
    if not data or not data.get('response'): return 0, 0, 0
    h=0; d=0; a=0
    for m in data['response'][:10]:
        sc_h = m['goals']['home']; sc_a = m['goals']['away']
        if sc_h is None: continue
        res = "D"
        if sc_h > sc_a: res = "H"
        elif sc_a > sc_h: res = "A"
        if m['teams']['home']['id'] == h_id:
            if res == "H": h+=1
            elif res == "A": a+=1
            else: d+=1
        else:
            if res == "H": a+=1
            elif res == "A": h+=1
            else: d+=1
    return h, d, a

def get_injuries_count(fixture_id, home_team_name, away_team_name):
    data = call_api('injuries', {'fixture': fixture_id})
    if not data or not data.get('response'): return 0, 0
    h_c = 0; a_c = 0
    for item in data['response']:
        if item['team']['name'] == home_team_name: h_c += 1
        elif item['team']['name'] == away_team_name: a_c += 1
    return h_c, a_c

def get_best_odds(fixture_id):
    data = call_api('odds', {'fixture': fixture_id})
    if not data or not data.get('response'): return 0, 0, 0
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
    return 0, 0, 0

def safe_float(val):
    try: return float(val) if val is not None else 0.0
    except: return 0.0

def clean_percent_str(val_str):
    try: return int(float(str(val_str).replace('%', '')))
    except: return 0

# ================= V36 數學核心 =================
def calculate_split_expected_goals(h_id, a_id, standings_map, pred_data):
    api_h = 1.3; api_a = 1.0
    if pred_data:
        t = pred_data.get('teams', {})
        api_h = safe_float(t.get('home',{}).get('last_5',{}).get('goals',{}).get('for',{}).get('average'))
        api_a = safe_float(t.get('away',{}).get('last_5',{}).get('goals',{}).get('for',{}).get('average'))
    
    split_h = 0; split_a = 0; has_split = False
    h_stats = standings_map.get(h_id, {})
    a_stats = standings_map.get(a_id, {})
    
    if h_stats and a_stats:
        try:
            if h_stats['home_stats']['played'] > 2 and a_stats['away_stats']['played'] > 2:
                split_h = (h_stats['home_stats']['avg_goals_for'] + a_stats['away_stats']['avg_goals_against']) / 2.0
                split_a = (a_stats['away_stats']['avg_goals_for'] + h_stats['home_stats']['avg_goals_against']) / 2.0
                has_split = True
        except: pass
    
    if has_split:
        fh = max(0.1, (split_h * 0.7) + (api_h * 0.3))
        fa = max(0.1, (split_a * 0.7) + (api_a * 0.3))
        return fh, fa, "特化數據"
    return max(0.1, api_h), max(0.1, api_a), "API數據"

def poisson_prob(k, lam):
    if lam <= 0: return 0
    return (math.pow(lam, k) * math.exp(-lam)) / math.factorial(k)

def calculate_advanced_math_probs(h_exp, a_exp):
    prob_exact = {}
    for h in range(10):
        for a in range(10): prob_exact[(h, a)] = poisson_prob(h, h_exp) * poisson_prob(a, a_exp)
    
    h_win = sum(p for (h, a), p in prob_exact.items() if h > a)
    draw = sum(p for (h, a), p in prob_exact.items() if h == a)
    a_win = sum(p for (h, a), p in prob_exact.items() if a > h)
    
    o25 = sum(p for (h, a), p in prob_exact.items() if h+a > 2.5)
    btts = 1 - sum(p for (h, a), p in prob_exact.items() if h==0 or a==0)
    
    return {
        'h_win': h_win*100, 'draw': draw*100, 'a_win': a_win*100,
        'o25': o25*100, 'btts': btts*100
    }

def calculate_kelly_stake(prob, odds):
    if odds <= 1 or prob <= 0: return 0
    b = odds - 1; q = 1 - prob; f = (b * prob - q) / b
    return max(0, f * 100)

# ================= 主流程 =================
def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 V36.1 Unstoppable Edition (with Backup) 啟動...")
    
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    utc_now = datetime.now(pytz.utc)
    from_date = (utc_now - timedelta(days=1)).strftime('%Y-%m-%d')
    to_date = (utc_now + timedelta(days=3)).strftime('%Y-%m-%d')
    season = 2025
    
    print(f"📅 掃描範圍: {from_date} 至 {to_date}")
    cleaned_data = []
    
    # 預備一個變量來存儲高價值比賽，用於最後打印
    value_bets = []

    for lg_id, lg_name in LEAGUE_ID_MAP.items():
        print(f"   🔍 掃描 {lg_name}...")
        standings = get_league_standings(lg_id, season)
        
        fixtures_data = call_api('fixtures', {'league': lg_id, 'season': season, 'from': from_date, 'to': to_date})
        if not fixtures_data or not fixtures_data.get('response'): continue
        
        fixtures = fixtures_data['response']
        print(f"      👉 找到 {len(fixtures)} 場比賽")
        
        for item in fixtures:
            fix_id = item['fixture']['id']
            t_str = datetime.fromtimestamp(item['fixture']['timestamp'], pytz.utc).astimezone(hk_tz).strftime('%Y-%m-%d %H:%M')
            status = item['fixture']['status']['short']
            if status in ['FT','AET','PEN']: status_txt = '完場'
            elif status in ['1H','2H','HT','LIVE']: status_txt = '進行中'
            elif status in ['PST','CANC','ABD']: status_txt = '延遲/取消'
            else: status_txt = '未開賽'

            h_name = item['teams']['home']['name']; a_name = item['teams']['away']['name']
            h_id = item['teams']['home']['id']; a_id = item['teams']['away']['id']
            sc_h = item['goals']['home']; sc_a = item['goals']['away']

            # 數據獲取
            h_info = standings.get(h_id, {'rank':99, 'form':'N/A'})
            a_info = standings.get(a_id, {'rank':99, 'form':'N/A'})
            
            pred_resp = call_api('predictions', {'fixture': fix_id})
            pred_data = pred_resp['response'][0] if pred_resp and pred_resp.get('response') else None
            
            # 核心運算
            h_exp, a_exp, src = calculate_split_expected_goals(h_id, a_id, standings, pred_data)
            probs = calculate_advanced_math_probs(h_exp, a_exp)
            
            # 賠率與凱利
            odds_h, odds_d, odds_a = 0,0,0
            if status_txt != '完場': odds_h, odds_d, odds_a = get_best_odds(fix_id)
            
            # Value 檢測 (Edge Check)
            val_h = ""; val_a = ""
            edge_h = 0; edge_a = 0
            
            if odds_h > 0:
                implied = 1/odds_h
                edge_h = (probs['h_win']/100) - implied
                if edge_h > 0.05: val_h = "💰" # 5% Edge
                
            if odds_a > 0:
                implied = 1/odds_a
                edge_a = (probs['a_win']/100) - implied
                if edge_a > 0.05: val_a = "💰"

            # 如果有 Value，加入戰報列表
            if val_h or val_a:
                pick = f"主勝 ({h_name})" if val_h else f"客勝 ({a_name})"
                odds = odds_h if val_h else odds_a
                edge = edge_h if val_h else edge_a
                value_bets.append({
                    'League': lg_name, 'Match': f"{h_name} vs {a_name}", 
                    'Pick': pick, 'Odds': odds, 'Edge': f"{edge*100:.1f}%"
                })

            cleaned_data.append({
                '時間': t_str, '聯賽': lg_name, '主隊': h_name, '客隊': a_name, '狀態': status_txt,
                '主分': sc_h, '客分': sc_a, '主排名': h_info['rank'], '客排名': a_info['rank'],
                'xG主': round(h_exp,2), 'xG客': round(a_exp,2), '數據源': src,
                '主勝率%': round(probs['h_win']), '客勝率%': round(probs['a_win']),
                '大2.5%': round(probs['o25']), 'BTTS%': round(probs['btts']),
                '主賠': odds_h, '客賠': odds_a, '主Value': val_h, '客Value': val_a
            })
            
            print(f"         ✅ {h_name} vs {a_name} | xG: {h_exp:.2f}-{a_exp:.2f} {val_h}{val_a}")
            time.sleep(0.1)

    # ================= 數據保存與展示 =================
    if cleaned_data:
        df = pd.DataFrame(cleaned_data)
        
        # 1. 嘗試上傳 Google Sheet
        spreadsheet = get_google_spreadsheet()
        uploaded = False
        if spreadsheet:
            try:
                spreadsheet.sheet1.clear()
                spreadsheet.sheet1.update(range_name='A1', values=[df.columns.values.tolist()] + df.astype(str).values.tolist())
                print("\n✅ [成功] 數據已上傳至 Google Sheet！")
                uploaded = True
            except: print("\n❌ [失敗] Google Sheet 上傳中斷")
        else:
            print("\n⚠️ [跳過] 未檢測到 key.json，跳過 Google Sheet 上傳")

        # 2. 強制備份到 CSV (雙重保險)
        csv_name = "football_data_backup.csv"
        df.to_csv(csv_name, index=False, encoding='utf-8-sig')
        print(f"💾 [備份] 數據已保存至本地文件: {csv_name}")

        # 3. 控制台戰報 (直接顯示價值注項)
        if value_bets:
            print("\n" + "="*50)
            print("💎 今日精選 VALUE BETS (泊松模型優勢 > 5%) 💎")
            print("="*50)
            print(f"{'聯賽':<10} | {'比賽':<30} | {'推介':<20} | {'賠率':<6} | {'優勢'}")
            print("-" * 80)
            for v in value_bets:
                print(f"{v['League']:<10} | {v['Match']:<30} | {v['Pick']:<20} | {v['Odds']:<6} | {v['Edge']}")
            print("="*50 + "\n")
        else:
            print("\n今日無明顯 Value Bet，建議觀望。")

    else:
        print("⚠️ 無數據")

if __name__ == "__main__":
    main()
