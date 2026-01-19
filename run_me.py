import requests
import pandas as pd
import math
import time
import gspread
from datetime import datetime, timedelta
import pytz
from oauth2client.service_account import ServiceAccountCredentials
import os

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

# ================= Google Sheet =================
def get_google_spreadsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if os.path.exists("key.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        else:
            # 如果找不到 key.json，嘗試從環境變數讀取 (適用於 Streamlit Cloud 等環境)
            # 你需要確保 key.json 文件存在於同一目錄下
            print("⚠️ 找不到 key.json，請確保該文件存在。")
            return None
            
        client = gspread.authorize(creds)
        return client.open(GOOGLE_SHEET_NAME)
    except Exception as e:
        print(f"❌ Google Sheet 連接錯誤: {e}")
        return None

# ================= 數據獲取工具 (V36 核心升級) =================
def get_league_standings(league_id, season):
    """
    V36 升級：獲取詳細的主客場數據 (Home/Away Splits)
    """
    data = call_api('standings', {'league': league_id, 'season': season})
    standings_map = {}
    
    if not data or not data.get('response'):
        return standings_map

    try:
        # 處理不同聯賽結構 (部分聯賽有多個小組)
        standings_response = data['response'][0]['league']['standings']
        all_teams = []
        
        # 扁平化所有分組
        for group in standings_response:
            all_teams.extend(group)
            
        for team in all_teams:
            t_id = team['team']['id']
            
            # 提取主場數據
            h_played = team['home']['played']
            h_for = team['home']['goals']['for']
            h_against = team['home']['goals']['against']
            
            # 提取客場數據
            a_played = team['away']['played']
            a_for = team['away']['goals']['for']
            a_against = team['away']['goals']['against']
            
            standings_map[t_id] = {
                'rank': team['rank'],
                'form': team['form'], # 近況 WWLDW
                'points': team['points'],
                # V36 新增詳細數據
                'home_stats': {
                    'played': h_played,
                    'avg_goals_for': h_for / h_played if h_played > 0 else 0,
                    'avg_goals_against': h_against / h_played if h_played > 0 else 0
                },
                'away_stats': {
                    'played': a_played,
                    'avg_goals_for': a_for / a_played if a_played > 0 else 0,
                    'avg_goals_against': a_against / a_played if a_played > 0 else 0
                }
            }
    except:
        pass
        
    return standings_map

def get_h2h_stats(h_id, a_id):
    param_str = f"{h_id}-{a_id}"
    data = call_api('fixtures/headtohead', {'h2h': param_str})
    h_win = 0; draw = 0; a_win = 0
    if not data or not data.get('response'): return 0, 0, 0
    recent = data['response'][:10]
    for m in recent:
        s_h = m['goals']['home']; s_a = m['goals']['away']
        if s_h is None or s_a is None: continue
        res = "draw"
        if s_h > s_a: res = "home_win"
        elif s_a > s_h: res = "away_win"
        
        if m['teams']['home']['id'] == h_id:
            if res == "home_win": h_win += 1
            elif res == "away_win": a_win += 1
            else: draw += 1
        else:
            if res == "home_win": a_win += 1 
            elif res == "away_win": h_win += 1
            else: draw += 1
    return h_win, draw, a_win

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
    target = next((b for b in bks if b['id'] in [1, 6, 8, 2]), None) 
    if not target and bks: target = bks[0]
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
    """
    V36 核心：混合主客場特化數據與 API 近況
    """
    # 默認 API 數據 (Last 5)
    api_h_exp = 1.3; api_a_exp = 1.0
    if pred_data:
        t = pred_data.get('teams', {})
        api_h_exp = safe_float(t.get('home',{}).get('last_5',{}).get('goals',{}).get('for',{}).get('average'))
        api_a_exp = safe_float(t.get('away',{}).get('last_5',{}).get('goals',{}).get('for',{}).get('average'))

    # 特化數據 (Home vs Away)
    split_h_exp = 0; split_a_exp = 0
    has_split_data = False
    
    h_stats = standings_map.get(h_id, {})
    a_stats = standings_map.get(a_id, {})
    
    if h_stats and a_stats:
        try:
            # 主隊主場攻擊力 vs 客隊客場防守力
            h_home_att = h_stats['home_stats']['avg_goals_for']
            a_away_def = a_stats['away_stats']['avg_goals_against']
            
            # 客隊客場攻擊力 vs 主隊主場防守力
            a_away_att = a_stats['away_stats']['avg_goals_for']
            h_home_def = h_stats['home_stats']['avg_goals_against']
            
            # 只有當樣本數足夠時 (>2場) 才使用特化數據
            if h_stats['home_stats']['played'] > 2 and a_stats['away_stats']['played'] > 2:
                split_h_exp = (h_home_att + a_away_def) / 2.0
                split_a_exp = (a_away_att + h_home_def) / 2.0
                has_split_data = True
        except: pass

    # 加權混合 (如果有特化數據，權重 70% 特化，30% 近況)
    if has_split_data:
        final_h = (split_h_exp * 0.7) + (api_h_exp * 0.3)
        final_a = (split_a_exp * 0.7) + (api_a_exp * 0.3)
        # 修正：避免數據過小
        final_h = max(0.1, final_h)
        final_a = max(0.1, final_a)
        return final_h, final_a, "特化數據"
    else:
        # 如果是季初，只能用 API 數據
        return max(0.1, api_h_exp), max(0.1, api_a_exp), "API數據"

def poisson_prob(k, lam):
    if lam <= 0: return 0
    return (math.pow(lam, k) * math.exp(-lam)) / math.factorial(k)

def calculate_advanced_math_probs(h_exp, a_exp):
    prob_exact = {}
    for h in range(10):
        for a in range(10):
            prob_exact[(h, a)] = poisson_prob(h, h_exp) * poisson_prob(a, a_exp)

    o05 = sum(p for (h, a), p in prob_exact.items() if h+a > 0.5)
    o15 = sum(p for (h, a), p in prob_exact.items() if h+a > 1.5)
    o25 = sum(p for (h, a), p in prob_exact.items() if h+a > 2.5)
    o35 = sum(p for (h, a), p in prob_exact.items() if h+a > 3.5)
    
    h_win = sum(p for (h, a), p in prob_exact.items() if h > a)
    draw = sum(p for (h, a), p in prob_exact.items() if h == a)
    a_win = sum(p for (h, a), p in prob_exact.items() if a > h)
    
    norm = h_win + a_win + 0.00001
    
    # 亞盤模擬
    h_win_1 = sum(p for (h, a), p in prob_exact.items() if h - a == 1)
    a_win_1 = sum(p for (h, a), p in prob_exact.items() if a - h == 1)
    
    fts_h = (h_exp / (h_exp + a_exp + 0.001)) * (1 - prob_exact.get((0,0),0))
    fts_a = (a_exp / (h_exp + a_exp + 0.001)) * (1 - prob_exact.get((0,0),0))
    btts = 1 - sum(p for (h, a), p in prob_exact.items() if h==0 or a==0)
    
    # 半場 (估算)
    ht_h_exp = h_exp * 0.42; ht_a_exp = a_exp * 0.42
    ht_prob = {}
    for h in range(6):
        for a in range(6):
            ht_prob[(h, a)] = poisson_prob(h, ht_h_exp) * poisson_prob(a, ht_a_exp)
    ht_o05 = sum(p for (h, a), p in ht_prob.items() if h+a > 0.5)
    ht_o15 = sum(p for (h, a), p in ht_prob.items() if h+a > 1.5)
    ht_o25 = sum(p for (h, a), p in ht_prob.items() if h+a > 2.5)

    return {
        'o05': round(o05*100), 'o15': round(o15*100), 'o25': round(o25*100), 'o35': round(o35*100),
        'ht_o05': round(ht_o05*100), 'ht_o15': round(ht_o15*100), 'ht_o25': round(ht_o25*100),
        'ah_level_h': round((h_win/norm)*100), 'ah_level_a': round((a_win/norm)*100),
        'ah_m025_h': round(h_win*100), 'ah_m025_a': round(a_win*100),
        'ah_p025_h': round((h_win+draw)*100), 'ah_p025_a': round((a_win+draw)*100),
        'ah_m075_h': round((h_win - h_win_1*0.5)*100), 'ah_m075_a': round((a_win - a_win_1*0.5)*100),
        'ah_p075_h': round((h_win+draw)*100), 'ah_p075_a': round((a_win+draw)*100),
        'ah_m125_h': round((h_win-h_win_1)*100), 'ah_m125_a': round((a_win-a_win_1)*100),
        'ah_p125_h': round((h_win+draw+a_win_1)*100), 'ah_p125_a': round((a_win+draw+h_win_1)*100),
        'ah_m2_h': 0, 'ah_m2_a': 0, 'ah_p2_h': 0, 'ah_p2_a': 0, # 簡化
        'fts_h': round(fts_h*100), 'fts_a': round(fts_a*100), 'btts': round(btts*100)
    }

def calculate_kelly_stake(prob, odds):
    if odds <= 1 or prob <= 0: return 0
    b = odds - 1; q = 1 - prob; f = (b * prob - q) / b
    return max(0, f * 100)

# ================= 主流程 =================
def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 V36.0 Professional (Home/Away Splits) 啟動...")
    
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    utc_now = datetime.now(pytz.utc)
    from_date = (utc_now - timedelta(days=1)).strftime('%Y-%m-%d')
    to_date = (utc_now + timedelta(days=3)).strftime('%Y-%m-%d')
    season = 2025 # 請確保賽季 ID 正確
    
    print(f"📅 掃描範圍: {from_date} 至 {to_date}")
    cleaned_data = []
    
    for lg_id, lg_name in LEAGUE_ID_MAP.items():
        print(f"   🔍 掃描 {lg_name}...")
        
        # 1. 獲取並處理積分榜 (主客場特化)
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

            h_id = item['teams']['home']['id']; a_id = item['teams']['away']['id']
            h_name = item['teams']['home']['name']; a_name = item['teams']['away']['name']
            sc_h = item['goals']['home']; sc_a = item['goals']['away']
            score_txt = f"{int(sc_h)}-{int(sc_a)}" if sc_h is not None else ""

            # 獲取 Standings 資訊
            h_info = standings.get(h_id, {'rank':99, 'form':'N/A'})
            a_info = standings.get(a_id, {'rank':99, 'form':'N/A'})

            # API Prediction & Odds
            pred_resp = call_api('predictions', {'fixture': fix_id})
            api_h_win=0; api_a_win=0; api_draw=0; advice="N/A"; conf=0
            pred_data = None
            
            if pred_resp and pred_resp.get('response'):
                pred_data = pred_resp['response'][0]
                api_h_win = clean_percent_str(pred_data['predictions']['percent']['home'])
                api_draw = clean_percent_str(pred_data['predictions']['percent']['draw'])
                api_a_win = clean_percent_str(pred_data['predictions']['percent']['away'])
                advice = pred_data['predictions'].get('advice', 'N/A')
                conf = max(api_h_win, api_draw, api_a_win)

            # V36 核心計算：主客場特化 xG
            h_exp, a_exp, data_source = calculate_split_expected_goals(h_id, a_id, standings, pred_data)
            math_probs = calculate_advanced_math_probs(h_exp, a_exp)
            
            # 其他數據
            h2h_h, h2h_d, h2h_a = get_h2h_stats(h_id, a_id)
            inj_h, inj_a = 0, 0
            odds_h=0; odds_d=0; odds_a=0
            if status_txt != '完場':
                inj_h, inj_a = get_injuries_count(fix_id, h_name, a_name)
                odds_h, odds_d, odds_a = get_best_odds(fix_id)
            
            kelly_h = calculate_kelly_stake(api_h_win/100, odds_h)
            kelly_a = calculate_kelly_stake(api_a_win/100, odds_a)

            # Value Check
            val_h = "❌"; val_a = "❌"
            if odds_h > 0 and (api_h_win/100) > (1/odds_h)*1.05: val_h = "💰"
            if odds_a > 0 and (api_a_win/100) > (1/odds_a)*1.05: val_a = "💰"

            cleaned_data.append({
                '時間': t_str, '聯賽': lg_name, '主隊': h_name, '客隊': a_name,
                '狀態': status_txt, '主分': sc_h if sc_h is not None else "", '客分': sc_a if sc_a is not None else "",
                
                '主排名': h_info['rank'], '客排名': a_info['rank'],
                '主走勢': h_info['form'], '客走勢': a_info['form'],
                '主Value': val_h, '客Value': val_a,
                '數據源': data_source, # 顯示是 API 還是 特化數據

                '主勝率': api_h_win, '和局率': api_draw, '客勝率': api_a_win,
                'xG主': round(h_exp, 2), 'xG客': round(a_exp, 2), # 新增 xG 顯示
                
                '大0.5': math_probs['o05'], '大1.5': math_probs['o15'],
                '大2.5': math_probs['o25'], '大3.5': math_probs['o35'],
                'HT0.5': math_probs['ht_o05'], 'HT1.5': math_probs['ht_o15'], 'HT2.5': math_probs['ht_o25'],
                'FTS主': math_probs['fts_h'], 'FTS客': math_probs['fts_a'], 'BTTS': math_probs['btts'],
                
                '主平': math_probs['ah_level_h'], '主0/-0.5': math_probs['ah_m025_h'], 
                '主-0.5/-1': math_probs['ah_m075_h'], '主-1/-1.5': math_probs['ah_m125_h'],
                '主0/+0.5': math_probs['ah_p025_h'], '主+0.5/+1': math_probs['ah_p075_h'], '主+1/+1.5': math_probs['ah_p125_h'],
                
                '客平': math_probs['ah_level_a'], '客0/-0.5': math_probs['ah_m025_a'], 
                '客-0.5/-1': math_probs['ah_m075_a'], '客-1/-1.5': math_probs['ah_m125_a'],
                '客0/+0.5': math_probs['ah_p025_a'], '客+0.5/+1': math_probs['ah_p075_a'], '客+1/+1.5': math_probs['ah_p125_a'],

                '主賠': odds_h, '客賠': odds_a, '凱利主': round(kelly_h), '凱利客': round(kelly_a),
                '推介': advice, '信心': conf,
                '主傷': inj_h, '客傷': inj_a,
                'H2H主': h2h_h, 'H2H和': h2h_d, 'H2H客': h2h_a
            })
            print(f"         ✅ {h_name} vs {a_name} | xG: {h_exp:.2f}-{a_exp:.2f} ({data_source})")
            time.sleep(0.15)

    if cleaned_data:
        df = pd.DataFrame(cleaned_data)
        cols = ['時間','聯賽','主隊','客隊','狀態','主分','客分',
                '主排名','客排名','主走勢','客走勢','主Value','客Value','數據源',
                '主勝率','和局率','客勝率','xG主','xG客',
                '大0.5','大1.5','大2.5','大3.5',
                'HT0.5','HT1.5','HT2.5',
                'FTS主','FTS客','BTTS',
                '主平','主0/-0.5','主-0.5/-1','主-1/-1.5','主0/+0.5','主+0.5/+1','主+1/+1.5',
                '客平','客0/-0.5','客-0.5/-1','客-1/-1.5','客0/+0.5','客+0.5/+1','客+1/+1.5',
                '主賠','客賠','凱利主','凱利客','推介','信心',
                '主傷','客傷','H2H主','H2H和','H2H客']
        
        for c in cols:
            if c not in df.columns: df[c] = 0
            
        df = df.reindex(columns=cols, fill_value='')
        
        spreadsheet = get_google_spreadsheet()
        if spreadsheet:
            try: 
                spreadsheet.sheet1.clear()
                spreadsheet.sheet1.update(range_name='A1', values=[df.columns.values.tolist()] + df.astype(str).values.tolist())
                print("✅ V36.0 數據上傳成功！")
            except Exception as e: print(f"❌ 上傳失敗: {e}")
    else:
        print("⚠️ 無數據")

if __name__ == "__main__":
    main()
