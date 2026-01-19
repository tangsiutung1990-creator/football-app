import requests
import pandas as pd
import math
import time
import gspread
from datetime import datetime, timedelta
import pytz
from oauth2client.service_account import ServiceAccountCredentials

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
        creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        client = gspread.authorize(creds)
        return client.open(GOOGLE_SHEET_NAME)
    except Exception as e:
        print(f"❌ Google Sheet 連接錯誤: {e}")
        return None

# ================= 數據獲取工具 =================
def get_league_standings(league_id, season):
    """
    獲取聯賽積分榜，建立 {team_id: {'rank': 1, 'form': 'WWLDW'}} 的映射表
    """
    data = call_api('standings', {'league': league_id, 'season': season})
    standings_map = {}
    
    if not data or not data.get('response'):
        return standings_map

    try:
        # 大部分聯賽是 response[0]['league']['standings'][0] (單一分組)
        # 美職/墨超等可能是多組，這裡簡化處理取第一組或扁平化
        standings_list = data['response'][0]['league']['standings']
        
        # 扁平化處理所有分組 (針對美職聯等多區制)
        all_teams = []
        for group in standings_list:
            all_teams.extend(group)
            
        for team_info in all_teams:
            t_id = team_info['team']['id']
            rank = team_info['rank']
            form = team_info['form'] # e.g. "WWLDW"
            points = team_info['points']
            standings_map[t_id] = {
                'rank': rank,
                'form': form,
                'points': points
            }
    except:
        pass
        
    return standings_map

def get_injuries_count(fixture_id, home_team_name, away_team_name):
    data = call_api('injuries', {'fixture': fixture_id})
    if not data or not data.get('response'): return 0, 0
    h_count = 0; a_count = 0
    for item in data['response']:
        t_name = item['team']['name']
        if t_name == home_team_name: h_count += 1
        elif t_name == away_team_name: a_count += 1
    return h_count, a_count

def get_best_odds(fixture_id):
    data = call_api('odds', {'fixture': fixture_id})
    if not data or not data.get('response'): return 0, 0, 0
    bookmakers = data['response'][0]['bookmakers']
    target_book = next((b for b in bookmakers if b['id'] in [1, 6, 8, 2, 3, 10]), None) 
    if not target_book and bookmakers: target_book = bookmakers[0]
    
    if target_book:
        winner_bet = next((b for b in target_book['bets'] if b['name'] == 'Match Winner'), None)
        if winner_bet:
            h=0; d=0; a=0
            for o in winner_bet['values']:
                if o['value'] == 'Home': h = float(o['odd'])
                if o['value'] == 'Draw': d = float(o['odd'])
                if o['value'] == 'Away': a = float(o['odd'])
            return h, d, a
    return 0, 0, 0

def get_h2h_stats(h_id, a_id):
    param_str = f"{h_id}-{a_id}"
    data = call_api('fixtures/headtohead', {'h2h': param_str})
    h_win = 0; draw = 0; a_win = 0
    if not data or not data.get('response'): return 0, 0, 0
    recent_matches = data['response'][:10]
    for m in recent_matches:
        past_home_score = m['goals']['home']
        past_away_score = m['goals']['away']
        if past_home_score is None or past_away_score is None: continue
        result = "draw"
        if past_home_score > past_away_score: result = "home_win"
        elif past_away_score > past_home_score: result = "away_win"
        
        if m['teams']['home']['id'] == h_id:
            if result == "home_win": h_win += 1
            elif result == "away_win": a_win += 1
            else: draw += 1
        else:
            if result == "home_win": a_win += 1 
            elif result == "away_win": h_win += 1
            else: draw += 1
    return h_win, draw, a_win

def safe_float(val):
    try:
        if val is None or val == '': return 0.0
        return float(val)
    except: return 0.0

def get_strict_api_goals_exp(pred_data):
    if not pred_data: return 0, 0, 0.5, 0.5, 0.5, 0.5
    teams = pred_data.get('teams', {})
    home_data = teams.get('home', {})
    away_data = teams.get('away', {})
    h_exp = safe_float(home_data.get('last_5', {}).get('goals', {}).get('for', {}).get('average'))
    a_exp = safe_float(away_data.get('last_5', {}).get('goals', {}).get('for', {}).get('average'))
    if h_exp == 0:
        h_exp = safe_float(home_data.get('league', {}).get('goals', {}).get('for', {}).get('average', {}).get('total'))
    if a_exp == 0:
        a_exp = safe_float(away_data.get('league', {}).get('goals', {}).get('for', {}).get('average', {}).get('total'))
    
    cmp = pred_data.get('comparison', {})
    def parse_pct(s): return safe_float(str(s).replace('%',''))
    att_h = parse_pct(cmp.get('att', {}).get('home', "0%"))
    att_a = parse_pct(cmp.get('att', {}).get('away', "0%"))
    def_h = parse_pct(cmp.get('def', {}).get('home', "0%"))
    def_a = parse_pct(cmp.get('def', {}).get('away', "0%"))
    return h_exp, a_exp, att_h, att_a, def_h, def_a

# ================= 數學與價值計算 =================
def poisson_prob(k, lam):
    if lam <= 0: return 0
    return (math.pow(lam, k) * math.exp(-lam)) / math.factorial(k)

def calculate_advanced_math_probs(h_exp, a_exp):
    if h_exp == 0 and a_exp == 0:
        return {k: 0 for k in ['o05','o15','o25','o35','ht_o05','ht_o15','ht_o25',
                               'ah_level_h','ah_level_a','ah_m025_h','ah_m025_a',
                               'ah_p025_h','ah_p025_a','ah_m075_h','ah_m075_a',
                               'ah_p075_h','ah_p075_a','ah_m125_h','ah_m125_a',
                               'ah_p125_h','ah_p125_a','ah_m2_h','ah_m2_a',
                               'ah_p2_h','ah_p2_a','fts_h','fts_a','btts']}

    prob_exact_score = {}
    for h in range(10):
        for a in range(10):
            p = poisson_prob(h, h_exp) * poisson_prob(a, a_exp)
            prob_exact_score[(h, a)] = p

    o05 = sum(p for (h, a), p in prob_exact_score.items() if h+a > 0.5)
    o15 = sum(p for (h, a), p in prob_exact_score.items() if h+a > 1.5)
    o25 = sum(p for (h, a), p in prob_exact_score.items() if h+a > 2.5)
    o35 = sum(p for (h, a), p in prob_exact_score.items() if h+a > 3.5)
    
    h_win = sum(p for (h, a), p in prob_exact_score.items() if h > a)
    draw = sum(p for (h, a), p in prob_exact_score.items() if h == a)
    a_win = sum(p for (h, a), p in prob_exact_score.items() if a > h)
    
    h_win_1 = sum(p for (h, a), p in prob_exact_score.items() if h - a == 1)
    a_win_1 = sum(p for (h, a), p in prob_exact_score.items() if a - h == 1)
    h_win_2 = sum(p for (h, a), p in prob_exact_score.items() if h - a == 2)
    
    norm = h_win + a_win + 0.00001
    ah_level_h = h_win / norm
    ah_level_a = a_win / norm
    ah_m025_h = h_win
    ah_m025_a = a_win
    ah_p025_h = h_win + draw
    ah_p025_a = a_win + draw
    ah_m075_h = h_win - (h_win_1 * 0.5)
    ah_m075_a = a_win - (a_win_1 * 0.5)
    ah_m125_h = h_win - h_win_1
    ah_m125_a = a_win - a_win_1
    
    ht_prob = {}
    for h in range(6):
        for a in range(6):
            ht_prob[(h, a)] = poisson_prob(h, h_exp*0.42) * poisson_prob(a, a_exp*0.42)
    ht_o05 = sum(p for (h, a), p in ht_prob.items() if h+a > 0.5)
    ht_o15 = sum(p for (h, a), p in ht_prob.items() if h+a > 1.5)
    ht_o25 = sum(p for (h, a), p in ht_prob.items() if h+a > 2.5)
    
    prob_0_0 = prob_exact_score.get((0,0), 0)
    denom = h_exp + a_exp + 0.00001
    fts_h = (h_exp / denom) * (1 - prob_0_0)
    fts_a = (a_exp / denom) * (1 - prob_0_0)
    btts = 1 - (sum(p for (h, a), p in prob_exact_score.items() if h==0 or a==0))

    return {
        'o05': round(o05*100), 'o15': round(o15*100), 'o25': round(o25*100), 'o35': round(o35*100),
        'ht_o05': round(ht_o05*100), 'ht_o15': round(ht_o15*100), 'ht_o25': round(ht_o25*100),
        'ah_level_h': round(ah_level_h*100), 'ah_level_a': round(ah_level_a*100),
        'ah_m025_h': round(ah_m025_h*100), 'ah_m025_a': round(ah_m025_a*100),
        'ah_p025_h': round(ah_p025_h*100), 'ah_p025_a': round(ah_p025_a*100),
        'ah_m075_h': round(h_win*100), 'ah_m075_a': round(a_win*100),
        'ah_p075_h': round((h_win+draw)*100), 'ah_p075_a': round((a_win+draw)*100),
        'ah_m125_h': round(ah_m125_h*100), 'ah_m125_a': round(ah_m125_a*100),
        'ah_p125_h': round((h_win+draw+a_win_1)*100), 'ah_p125_a': round((a_win+draw+h_win_1)*100),
        'ah_m2_h': round((h_win-h_win_1-h_win_2)*100), 'ah_m2_a': round((a_win-a_win_1)*100),
        'ah_p2_h': 0, 'ah_p2_a': 0,
        'fts_h': round(fts_h*100), 'fts_a': round(fts_a*100), 'btts': round(btts*100)
    }

def calculate_kelly_stake(prob, odds):
    if odds <= 1 or prob <= 0: return 0
    b = odds - 1
    q = 1 - prob
    f = (b * prob - q) / b
    return max(0, f * 100)

def clean_percent_str(val_str):
    if not val_str: return 0
    try: return int(float(str(val_str).replace('%', '')))
    except: return 0

# ================= 主流程 =================
def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 V35.0 Context-Aware Edition 啟動...")
    
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    utc_now = datetime.now(pytz.utc)
    from_date = (utc_now - timedelta(days=1)).strftime('%Y-%m-%d')
    to_date = (utc_now + timedelta(days=3)).strftime('%Y-%m-%d')
    season = 2025 
    
    print(f"📅 掃描範圍: {from_date} 至 {to_date}")
    
    cleaned_data = []
    
    for lg_id, lg_name in LEAGUE_ID_MAP.items():
        print(f"   🔍 掃描 {lg_name}...")
        
        # 1. 優先獲取該聯賽積分榜 (發揮 API 潛力：獲取排名和走勢)
        standings = get_league_standings(lg_id, season)
        if standings:
            print(f"      📊 已獲取積分榜數據 (包含 {len(standings)} 隊)")
        
        fixtures_data = call_api('fixtures', {'league': lg_id, 'season': season, 'from': from_date, 'to': to_date})
        
        if not fixtures_data or not fixtures_data.get('response'): continue
        fixtures = fixtures_data['response']
        print(f"      👉 找到 {len(fixtures)} 場比賽")
        
        for item in fixtures:
            fix_id = item['fixture']['id']
            t_str = datetime.fromtimestamp(item['fixture']['timestamp'], pytz.utc).astimezone(hk_tz).strftime('%Y-%m-%d %H:%M')
            s_short = item['fixture']['status']['short']
            
            if s_short in ['PST', 'CANC', 'ABD']: status = '延遲/取消'
            elif s_short in ['FT', 'AET', 'PEN']: status = '完場'
            elif s_short in ['1H', '2H', 'HT', 'LIVE']: status = '進行中'
            else: status = '未開賽'

            h_id = item['teams']['home']['id']
            a_id = item['teams']['away']['id']
            h_name = item['teams']['home']['name']
            a_name = item['teams']['away']['name']
            sc_h = item['goals']['home']; sc_a = item['goals']['away']
            score_h_display = str(int(sc_h)) if sc_h is not None else ""
            score_a_display = str(int(sc_a)) if sc_a is not None else ""

            # 從 standings 提取排名和走勢
            h_rank_info = standings.get(h_id, {'rank': 99, 'form': 'N/A'})
            a_rank_info = standings.get(a_id, {'rank': 99, 'form': 'N/A'})
            
            h_rank = h_rank_info['rank']
            a_rank = h_rank_info['rank']
            h_form_str = h_rank_info['form'] # e.g. WWLLD
            a_form_str = a_rank_info['form']

            # API 預測
            pred_resp = call_api('predictions', {'fixture': fix_id})
            
            api_h_win=0; api_draw=0; api_a_win=0
            advice="數據不足"; confidence_score = 0
            att_h=0; att_a=0; def_h=0; def_a=0
            h_final_exp = 0; a_final_exp = 0
            
            if pred_resp and pred_resp.get('response'):
                pred = pred_resp['response'][0]
                api_h_win = clean_percent_str(pred['predictions']['percent']['home'])
                api_draw = clean_percent_str(pred['predictions']['percent']['draw'])
                api_a_win = clean_percent_str(pred['predictions']['percent']['away'])
                advice = pred['predictions'].get('advice', '觀望')
                h_final_exp, a_final_exp, att_h, att_a, def_h, def_a = get_strict_api_goals_exp(pred)
                confidence_score = max(api_h_win, api_draw, api_a_win)

            h2h_h, h2h_d, h2h_a = get_h2h_stats(h_id, a_id)
            
            inj_h, inj_a = 0, 0
            odds_h=0; odds_d=0; odds_a=0
            if status != '完場':
                inj_h, inj_a = get_injuries_count(fix_id, h_name, a_name)
                odds_h, odds_d, odds_a = get_best_odds(fix_id)

            math_probs = calculate_advanced_math_probs(h_final_exp, a_final_exp)
            kelly_h = calculate_kelly_stake(api_h_win/100, odds_h)
            kelly_a = calculate_kelly_stake(api_a_win/100, odds_a)
            
            # 價值判斷 (Value Bet)
            # 賠率隱含勝率 = 1/賠率。如果 API 勝率 > 隱含勝率，就是 Value
            val_h = "❌"
            if odds_h > 0:
                implied_h = 1.0 / odds_h
                if (api_h_win / 100.0) > implied_h * 1.05: val_h = "💰" # 5% buffer

            val_a = "❌"
            if odds_a > 0:
                implied_a = 1.0 / odds_a
                if (api_a_win / 100.0) > implied_a * 1.05: val_a = "💰"

            cleaned_data.append({
                '時間': t_str, '聯賽': lg_name, '主隊': h_name, '客隊': a_name,
                '狀態': status, '主分': score_h_display, '客分': score_a_display,
                
                # 新增 Context 字段
                '主排名': h_rank, '客排名': a_rank,
                '主走勢': h_form_str, '客走勢': a_form_str,
                '主Value': val_h, '客Value': val_a,

                '主勝率': api_h_win, '和局率': api_draw, '客勝率': api_a_win,
                '大0.5': math_probs['o05'], '大1.5': math_probs['o15'],
                '大2.5': math_probs['o25'], '大3.5': math_probs['o35'],
                'HT0.5': math_probs['ht_o05'], 'HT1.5': math_probs['ht_o15'], 'HT2.5': math_probs['ht_o25'],
                'FTS主': math_probs['fts_h'], 'FTS客': math_probs['fts_a'], 'BTTS': math_probs['btts'],
                
                '主平': math_probs['ah_level_h'], '主0/-0.5': math_probs['ah_m025_h'], 
                '主-0.5/-1': math_probs['ah_m075_h'], '主-1/-1.5': math_probs['ah_m125_h'],
                '主0/+0.5': math_probs['ah_p025_h'], '主+0.5/+1': math_probs['ah_p075_h'], '主+1/+1.5': math_probs['ah_p125_h'],
                '主-2': math_probs['ah_m2_h'], '主+2': math_probs['ah_p2_h'],
                
                '客平': math_probs['ah_level_a'], '客0/-0.5': math_probs['ah_m025_a'], 
                '客-0.5/-1': math_probs['ah_m075_a'], '客-1/-1.5': math_probs['ah_m125_a'],
                '客0/+0.5': math_probs['ah_p025_a'], '客+0.5/+1': math_probs['ah_p075_a'], '客+1/+1.5': math_probs['ah_p125_a'],
                '客-2': math_probs['ah_m2_a'], '客+2': math_probs['ah_p2_a'],

                '主賠': odds_h, '客賠': odds_a, '凱利主': round(kelly_h), '凱利客': round(kelly_a),
                '推介': advice, '信心': confidence_score,
                '主狀態': h_form_str, '客狀態': a_form_str, # 使用真實走勢取代百分比
                '主攻': round(att_h), '客攻': round(att_a), 
                '主防': round(def_h), '客防': round(def_a),
                '主傷': inj_h, '客傷': inj_a,
                'H2H主': h2h_h, 'H2H和': h2h_d, 'H2H客': h2h_a
            })
            print(f"         ✅ {h_name}[#{h_rank}] vs {a_name}[#{a_rank}] | Form: {h_form_str} vs {a_form_str}")
            time.sleep(0.15)

    if cleaned_data:
        df = pd.DataFrame(cleaned_data)
        # 確保所有列都存在
        cols = ['時間','聯賽','主隊','客隊','狀態','主分','客分',
                '主排名','客排名','主走勢','客走勢','主Value','客Value',
                '主勝率','和局率','客勝率',
                '大0.5','大1.5','大2.5','大3.5',
                'HT0.5','HT1.5','HT2.5',
                'FTS主','FTS客','BTTS',
                '主平','主0/-0.5','主-0.5/-1','主-1/-1.5','主0/+0.5','主+0.5/+1','主+1/+1.5','主-2','主+2',
                '客平','客0/-0.5','客-0.5/-1','客-1/-1.5','客0/+0.5','客+0.5/+1','客+1/+1.5','客-2','客+2',
                '主賠','客賠','凱利主','凱利客','推介','信心',
                '主狀態','客狀態','主攻','客攻','主防','客防','主傷','客傷',
                'H2H主','H2H和','H2H客']
        
        for c in cols:
            if c not in df.columns: df[c] = 0
            
        df = df.reindex(columns=cols, fill_value='')
        
        spreadsheet = get_google_spreadsheet()
        if spreadsheet:
            try: 
                spreadsheet.sheet1.clear()
                spreadsheet.sheet1.update(range_name='A1', values=[df.columns.values.tolist()] + df.astype(str).values.tolist())
                print("✅ V35.0 數據上傳成功！")
            except Exception as e: print(f"❌ 上傳失敗: {e}")
    else:
        print("⚠️ 無數據")

if __name__ == "__main__":
    main()
