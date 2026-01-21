import requests
import pandas as pd
import math
import time
import gspread
from datetime import datetime, timedelta
import pytz
from oauth2client.service_account import ServiceAccountCredentials
import os
import streamlit as st

# ================= 設定區 =================
API_KEY = None

# 嘗試從 Streamlit Secrets 讀取
try:
    if "api" in st.secrets and "key" in st.secrets["api"]:
        API_KEY = st.secrets["api"]["key"]
except FileNotFoundError:
    pass 

if not API_KEY:
    API_KEY = os.getenv("FOOTBALL_API_KEY")

if not API_KEY:
    print("⚠️ 警告: 未找到 API Key。請配置 secrets.toml 或環境變數 FOOTBALL_API_KEY")

BASE_URL = 'https://v3.football.api-sports.io'
GOOGLE_SHEET_NAME = "數據上傳" 
CSV_FILENAME = "football_data_backup.csv" 

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
    if not API_KEY: return None
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-apisports-key': API_KEY}
    url = f"{BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("errors") and isinstance(data['errors'], list) and len(data['errors']) > 0: return None
            return data
        elif response.status_code == 429:
            time.sleep(5)
            return None
        else: return None
    except: return None

# ================= Google Sheet =================
def get_google_spreadsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        creds = None
        try:
            if "gcp_service_account" in st.secrets:
                creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        except: pass
        
        if not creds and os.path.exists("key.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
            
        if not creds:
            print("⚠️ 未找到 Google Credentials，跳過上傳")
            return None
            
        client = gspread.authorize(creds)
        return client.open(GOOGLE_SHEET_NAME)
    except Exception as e:
        print(f"⚠️ Google Sheet 連接失敗: {e}")
        return None

# ================= 數據獲取工具 =================
def get_league_standings(league_id, season):
    data = call_api('standings', {'league': league_id, 'season': season})
    standings_map = {}
    if not data or not data.get('response'): return standings_map
    try:
        for group in data['response'][0]['league']['standings']:
            for team in group:
                t_id = team['team']['id']
                h_s = team['home']; a_s = team['away']
                standings_map[t_id] = {
                    'rank': team['rank'], 'form': team['form'],
                    'home_stats': {'played': h_s['played'], 'avg_goals_for': h_s['goals']['for']/(h_s['played'] or 1), 'avg_goals_against': h_s['goals']['against']/(h_s['played'] or 1)},
                    'away_stats': {'played': a_s['played'], 'avg_goals_for': a_s['goals']['for']/(a_s['played'] or 1), 'avg_goals_against': a_s['goals']['against']/(a_s['played'] or 1)}
                }
    except: pass
    return standings_map

def get_h2h_stats(h_id, a_id):
    data = call_api('fixtures/headtohead', {'h2h': f"{h_id}-{a_id}"})
    if not data or not data.get('response'): return 0, 0, 0
    h=0; d=0; a=0
    for m in data['response'][:10]:
        sc_h = m['goals']['home']; sc_a = m['goals']['away']
        if sc_h is None or sc_a is None: continue
        if sc_h > sc_a: h+=1
        elif sc_a > sc_h: a+=1
        else: d+=1
    return h, d, a

def get_best_odds(fixture_id):
    data = call_api('odds', {'fixture': fixture_id})
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

def safe_float(val):
    try: return float(val) if val is not None else 0.0
    except: return 0.0

# ================= 數學核心 =================
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

def calculate_ah_probability(prob_exact, handicap_line, team='home'):
    """
    計算亞盤勝率
    handicap_line: 相對於主隊的讓球 (例如 -0.5, +0.5)
    """
    win_prob = 0
    # 遍歷矩陣中所有可能的比分 (h, a)
    for (h, a), prob in prob_exact.items():
        # 亞盤計算邏輯：主隊得分 + 讓球 > 客隊得分
        if team == 'home':
            if (h + handicap_line) > a:
                win_prob += prob
            elif (h + handicap_line) == a:
                # 走盤情況，這裡暫時不計入勝率，或者可以算一半，這裡算輸贏盤所以不加
                pass
        else:
            # 客隊視角：客隊得分 - 讓球 > 主隊得分 (或者說 客隊得分 + (讓球*-1) > 主隊)
            # 這裡簡化：如果盤口是 主-0.5，相當於 客+0.5
            if (a - handicap_line) > h:
                win_prob += prob
                
    return win_prob

def calculate_asian_handicap_data(h_xg, a_xg, prob_exact):
    diff = h_xg - a_xg
    pick = ""
    line = 0.0
    
    # 決定盤口和方向
    if diff >= 1.8: line = -1.5; pick = "主 -1.5"
    elif diff >= 1.3: line = -1.0; pick = "主 -1.0"
    elif diff >= 0.8: line = -0.5; pick = "主 -0.5"
    elif diff >= 0.3: line = -0.25; pick = "主 -0/0.5" # 0.25 較難計算精確勝率，這裡近似
    elif diff > -0.3: line = 0.0; pick = "平手 (0)"
    elif diff > -0.8: line = 0.25; pick = "客 -0/0.5" # 實際是主 +0.25
    elif diff > -1.3: line = 0.5; pick = "客 -0.5"     # 實際是主 +0.5
    elif diff > -1.8: line = 1.0; pick = "客 -1.0"     # 實際是主 +1.0
    else: line = 1.5; pick = "客 -1.5"                 # 實際是主 +1.5

    # 計算該推薦盤口的理論勝率
    # 這裡 line 始終是相對於主隊的。例如選 "客 -0.5"，意味著主隊是 +0.5
    # 若 pick 是客隊，我們計算客隊贏盤率
    
    target_team = 'home'
    calc_line = line
    
    if "客" in pick:
        target_team = 'away'
        # 如果顯示客 -0.5，代表數學上是 主 +0.5。
        # 在 calculate_ah_probability 中，若 team='away'，handicap_line 仍傳入主隊視角的讓球值
        # 例如 pick "客 -0.5" -> 主 +0.5 -> calc_line = 0.5
        pass
    
    prob = calculate_ah_probability(prob_exact, calc_line, target_team)
    return pick, prob * 100

def calculate_advanced_math_probs(h_exp, a_exp):
    prob_exact = {}
    for h in range(10):
        for a in range(10): prob_exact[(h, a)] = poisson_prob(h, h_exp) * poisson_prob(a, a_exp)
    
    h_win = sum(p for (h, a), p in prob_exact.items() if h > a)
    a_win = sum(p for (h, a), p in prob_exact.items() if a > h)
    draw = sum(p for (h, a), p in prob_exact.items() if h == a)
    
    # 全場大小球
    o05 = sum(p for (h, a), p in prob_exact.items() if h+a > 0.5)
    o15 = sum(p for (h, a), p in prob_exact.items() if h+a > 1.5)
    o25 = sum(p for (h, a), p in prob_exact.items() if h+a > 2.5)
    o35 = sum(p for (h, a), p in prob_exact.items() if h+a > 3.5)
    btts = 1 - sum(p for (h, a), p in prob_exact.items() if h==0 or a==0)

    # 半場估算 (假設半場 xG 約為全場 45%)
    ht_h_exp = h_exp * 0.45
    ht_a_exp = a_exp * 0.45
    ht_prob_exact = {}
    for h in range(6):
        for a in range(6): ht_prob_exact[(h, a)] = poisson_prob(h, ht_h_exp) * poisson_prob(a, ht_a_exp)
    
    ht_o05 = sum(p for (h, a), p in ht_prob_exact.items() if h+a > 0.5)
    ht_o15 = sum(p for (h, a), p in ht_prob_exact.items() if h+a > 1.5)

    # 亞盤建議與機率
    ah_pick, ah_prob = calculate_asian_handicap_data(h_exp, a_exp, prob_exact)

    return {
        'h_win': h_win*100, 'draw': draw*100, 'a_win': a_win*100,
        'o05': o05*100, 'o15': o15*100, 'o25': o25*100, 'o35': o35*100,
        'ht_o05': ht_o05*100, 'ht_o15': ht_o15*100,
        'btts': btts*100,
        'ah_pick': ah_pick,
        'ah_prob': ah_prob
    }

# ================= 主流程 =================
def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 V38.2 數據更新程序啟動...")
    if not API_KEY: print("⚠️ 警告: 缺少 API Key")

    hk_tz = pytz.timezone('Asia/Hong_Kong')
    hk_now = datetime.now(hk_tz)
    
    # 抓取範圍：昨天到今天
    yesterday_str = (hk_now - timedelta(days=1)).strftime('%Y-%m-%d')
    today_str = hk_now.strftime('%Y-%m-%d')
    
    season = 2025
    
    print(f"📅 掃描範圍: {yesterday_str} 至 {today_str}")
    cleaned_data = []

    for lg_id, lg_name in LEAGUE_ID_MAP.items():
        standings = get_league_standings(lg_id, season)
        # 一次抓兩天
        fixtures_data = call_api('fixtures', {'league': lg_id, 'season': season, 'from': yesterday_str, 'to': today_str})
        
        if not fixtures_data or not fixtures_data.get('response'): continue
        fixtures = fixtures_data['response']
        print(f"   ⚽ {lg_name}: {len(fixtures)} 場")
        
        for item in fixtures:
            fix_id = item['fixture']['id']
            match_date_str = datetime.fromtimestamp(item['fixture']['timestamp'], pytz.utc).astimezone(hk_tz).strftime('%Y-%m-%d')
            t_str = datetime.fromtimestamp(item['fixture']['timestamp'], pytz.utc).astimezone(hk_tz).strftime('%Y-%m-%d %H:%M')
            status_short = item['fixture']['status']['short']
            
            # 狀態分類邏輯
            if status_short in ['FT', 'AET', 'PEN']:
                status_txt = '完場'
            elif status_short in ['1H', 'HT', '2H', 'ET', 'BT', 'P', 'LIVE']:
                status_txt = '進行中'
            elif status_short in ['NS', 'TBD']:
                status_txt = '未開賽'
            elif status_short in ['PST', 'CANC', 'ABD', 'AWD', 'WO']:
                status_txt = '延期/取消'
            else:
                status_txt = '未開賽'

            h_name = item['teams']['home']['name']; a_name = item['teams']['away']['name']
            h_id = item['teams']['home']['id']; a_id = item['teams']['away']['id']
            sc_h = item['goals']['home']; sc_a = item['goals']['away']

            h_info = standings.get(h_id, {'rank': '?', 'form': '?????'})
            a_info = standings.get(a_id, {'rank': '?', 'form': '?????'})
            
            pred_resp = call_api('predictions', {'fixture': fix_id})
            pred_data = pred_resp['response'][0] if pred_resp and pred_resp.get('response') else None
            
            h_exp, a_exp, src = calculate_split_expected_goals(h_id, a_id, standings, pred_data)
            probs = calculate_advanced_math_probs(h_exp, a_exp)
            
            odds_h, odds_d, odds_a = 0,0,0
            # 只在未開賽或進行中抓取賠率，完場的可以跳過以節省請求
            if status_txt != '完場':
                odds_h, odds_d, odds_a = get_best_odds(fix_id)
            
            h2h_h, h2h_d, h2h_a = get_h2h_stats(h_id, a_id)

            val_h = ""; val_a = ""
            if odds_h > 0:
                if (probs['h_win']/100) > (1/odds_h): val_h = "💰"
            if odds_a > 0:
                if (probs['a_win']/100) > (1/odds_a): val_a = "💰"

            cleaned_data.append({
                '日期': match_date_str, 
                '時間': t_str, '聯賽': lg_name, '主隊': h_name, '客隊': a_name, '狀態': status_txt,
                '主分': sc_h if sc_h is not None else "", '客分': sc_a if sc_a is not None else "",
                '主排名': h_info['rank'], '客排名': a_info['rank'],
                '主走勢': h_info['form'], '客走勢': a_info['form'],
                '主Value': val_h, '客Value': val_a,
                'xG主': round(h_exp,2), 'xG客': round(a_exp,2), '數據源': src,
                '主勝率': round(probs['h_win']), '和率': round(probs['draw']), '客勝率': round(probs['a_win']),
                '大0.5': round(probs['o05']), 
                '大1.5': round(probs['o15']), 
                '大2.5': round(probs['o25']), 
                '大3.5': round(probs['o35']),
                '半大0.5': round(probs['ht_o05']), 
                '半大1.5': round(probs['ht_o15']),
                '亞盤': probs['ah_pick'],
                '亞盤率': round(probs['ah_prob']), # 新增
                'BTTS': round(probs['btts']),
                '主賠': odds_h, '客賠': odds_a,
                'H2H主': h2h_h, 'H2H和': h2h_d, 'H2H客': h2h_a
            })
            
            print(f"         ✅ {h_name} vs {a_name} | {probs['ah_pick']}")
            time.sleep(0.1)

    if cleaned_data:
        df = pd.DataFrame(cleaned_data)
        try:
            df.to_csv(CSV_FILENAME, index=False, encoding='utf-8-sig')
            print(f"\n💾 數據已備份至: {CSV_FILENAME}")
        except Exception as e: print(f"❌ CSV 保存失敗: {e}")

        spreadsheet = get_google_spreadsheet()
        if spreadsheet:
            try:
                spreadsheet.sheet1.clear()
                spreadsheet.sheet1.update(range_name='A1', values=[df.columns.values.tolist()] + df.astype(str).values.tolist())
                print("✅ Google Sheet 上傳成功")
            except Exception as e: print(f"❌ Google Sheet 上傳失敗: {e}")
    else:
        print("⚠️ 暫無賽事數據")

if __name__ == "__main__":
    main()
