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
MANUAL_TAB_NAME = "球隊身價表" 

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
        response = requests.get(url, headers=headers, params=params)
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
    except: return None

# ================= 數據獲取增強 =================
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

# ================= 純數學運算 =================
def poisson_prob(k, lam):
    if lam < 0: lam = 0
    return (math.pow(lam, k) * math.exp(-lam)) / math.factorial(k)

def calculate_advanced_math_probs(h_exp, a_exp):
    h_exp = float(h_exp); a_exp = float(a_exp)
    prob_exact_score = {}
    
    # 建立波膽矩陣
    for h in range(10):
        for a in range(10):
            p = poisson_prob(h, h_exp) * poisson_prob(a, a_exp)
            prob_exact_score[(h, a)] = p

    # 基礎勝平負
    h_win = sum(p for (h, a), p in prob_exact_score.items() if h > a)
    draw = sum(p for (h, a), p in prob_exact_score.items() if h == a)
    a_win = sum(p for (h, a), p in prob_exact_score.items() if a > h)
    
    # 輸贏球差
    h_win_1 = sum(p for (h, a), p in prob_exact_score.items() if h - a == 1)
    a_win_1 = sum(p for (h, a), p in prob_exact_score.items() if a - h == 1) # 主輸1球
    
    # === 亞盤精算 (Quarter Handicaps) ===
    # 1. 平手盤 (0): 贏盤率 = 贏 / (贏+輸)
    ah_0_h = h_win / (h_win + a_win + 0.00001)
    ah_0_a = a_win / (h_win + a_win + 0.00001)
    
    # 2. 0/-0.5 (-0.25): 贏全贏，和輸半
    # 這裡計算「期望回報率」概念的勝率: P(Win) + 0 (Draw是輸半)
    # 但為了顯示勝率，我們顯示「不輸全」的概率? 
    # 習慣上顯示 P(Win)。因為Draw是虧錢的。
    ah_minus_025_h = h_win 
    ah_minus_025_a = a_win
    
    # 3. 0/+0.5 (+0.25): 贏全贏，和贏半
    # 勝率 = P(Win) + 0.5 * P(Draw) (贏半算一半勝率)
    ah_plus_025_h = h_win + 0.5 * draw
    ah_plus_025_a = a_win + 0.5 * draw
    
    # 4. -0.5/-1 (-0.75): 贏2球全贏，贏1球贏半
    # 勝率 = P(Win>=2) + 0.5 * P(Win==1)
    ah_minus_075_h = (h_win - h_win_1) + 0.5 * h_win_1
    ah_minus_075_a = (a_win - a_win_1) + 0.5 * a_win_1
    
    # 5. +0.5/+1 (+0.75): 不敗全贏，輸1球輸半
    # 勝率 = P(Win+Draw) (輸1球是輸錢，所以不算在勝率)
    ah_plus_075_h = h_win + draw
    ah_plus_075_a = a_win + draw
    
    # 6. -1/-1.5 (-1.25): 贏2球全贏，贏1球輸半
    # 勝率 = P(Win>=2)
    ah_minus_125_h = h_win - h_win_1
    ah_minus_125_a = a_win - a_win_1
    
    # 7. +1/+1.5 (+1.25): 不敗全贏，輸1球贏半
    # 勝率 = P(Win+Draw) + 0.5 * P(Lose==1)
    ah_plus_125_h = (h_win + draw) + 0.5 * a_win_1
    ah_plus_125_a = (a_win + draw) + 0.5 * h_win_1

    # === 進球數據 ===
    # FTS (First Team to Score)
    prob_0_0 = prob_exact_score.get((0,0), 0)
    denom = h_exp + a_exp + 0.00001
    fts_h = (h_exp / denom) * (1 - prob_0_0)
    fts_a = (a_exp / denom) * (1 - prob_0_0)
    
    # BTTS
    btts = 1 - (sum(p for (h, a), p in prob_exact_score.items() if h==0 or a==0))

    # HT
    ht_prob = {}
    for h in range(6):
        for a in range(6):
            ht_prob[(h, a)] = poisson_prob(h, h_exp*0.45) * poisson_prob(a, a_exp*0.45)
    ht_o05 = sum(p for (h, a), p in ht_prob.items() if h+a > 0.5)
    ht_o15 = sum(p for (h, a), p in ht_prob.items() if h+a > 1.5)
    ht_o25 = sum(p for (h, a), p in ht_prob.items() if h+a > 2.5)

    return {
        # 亞盤數據 (HKJC Style)
        'ah_0_h': round(ah_0_h*100), 'ah_0_a': round(ah_0_a*100),
        'ah_m025_h': round(ah_minus_025_h*100), 'ah_m025_a': round(ah_minus_025_a*100),
        'ah_p025_h': round(ah_plus_025_h*100), 'ah_p025_a': round(ah_plus_025_a*100),
        'ah_m075_h': round(ah_minus_075_h*100), 'ah_m075_a': round(ah_minus_075_a*100),
        'ah_p075_h': round(ah_plus_075_h*100), 'ah_p075_a': round(ah_plus_075_a*100),
        'ah_m125_h': round(ah_minus_125_h*100), 'ah_m125_a': round(ah_minus_125_a*100),
        'ah_p125_h': round(ah_plus_125_h*100), 'ah_p125_a': round(ah_plus_125_a*100),
        
        # 進球數據
        'fts_h': round(fts_h*100), 'fts_a': round(fts_a*100), 'btts': round(btts*100),
        'ht_o05': round(ht_o05*100), 'ht_o15': round(ht_o15*100), 'ht_o25': round(ht_o25*100)
    }

def calculate_kelly_stake(prob, odds):
    if odds <= 1: return 0
    b = odds - 1; q = 1 - prob; f = (b * prob - q) / b
    return max(0, f * 100)

def clean_percent_str(val_str):
    if not val_str: return 0
    try: return int(float(str(val_str).replace('%', '')))
    except: return 0

# ================= 主流程 =================
def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 V29.0 API-Native (HKJC Handicap) 啟動...")
    
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    utc_now = datetime.now(pytz.utc)
    from_date = (utc_now - timedelta(days=7)).strftime('%Y-%m-%d')
    to_date = (utc_now + timedelta(days=3)).strftime('%Y-%m-%d')
    season = 2025 
    
    print(f"📅 掃描範圍: {from_date} 至 {to_date}")
    
    cleaned_data = []
    
    for lg_id, lg_name in LEAGUE_ID_MAP.items():
        print(f"   🔍 掃描 {lg_name}...")
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

            h_name = item['teams']['home']['name']
            a_name = item['teams']['away']['name']
            sc_h = item['goals']['home']; sc_a = item['goals']['away']
            score_h_display = str(int(sc_h)) if sc_h is not None else ""
            score_a_display = str(int(sc_a)) if sc_a is not None else ""

            # API 預測
            pred_resp = call_api('predictions', {'fixture': fix_id})
            api_h_win=0; api_draw=0; api_a_win=0
            api_goals_h=1.2; api_goals_a=1.0
            advice="暫無"; confidence_score = 0
            form_h="50%"; form_a="50%"; att_h="50%"; att_a="50%"; def_h="50%"; def_a="50%"
            
            if pred_resp and pred_resp.get('response'):
                pred = pred_resp['response'][0]
                api_h_win = clean_percent_str(pred['predictions']['percent']['home'])
                api_draw = clean_percent_str(pred['predictions']['percent']['draw'])
                api_a_win = clean_percent_str(pred['predictions']['percent']['away'])
                advice = pred['predictions'].get('advice', '觀望')
                confidence_score = max(api_h_win, api_draw, api_a_win)
                try:
                    cmp = pred['comparison']
                    form_h = cmp.get('form', {}).get('home', "50%")
                    form_a = cmp.get('form', {}).get('away', "50%")
                    att_h = cmp.get('att', {}).get('home', "50%")
                    att_a = cmp.get('att', {}).get('away', "50%")
                    def_h = cmp.get('def', {}).get('home', "50%")
                    def_a = cmp.get('def', {}).get('away', "50%")
                    api_goals_h = float(pred['teams']['home']['last_5']['goals']['for']['average'])
                    api_goals_a = float(pred['teams']['away']['last_5']['goals']['for']['average'])
                    if api_goals_h == 0: api_goals_h = 0.5
                    if api_goals_a == 0: api_goals_a = 0.5
                except: pass

            inj_h, inj_a = 0, 0
            odds_h=0; odds_d=0; odds_a=0
            if status != '完場':
                inj_h, inj_a = get_injuries_count(fix_id, h_name, a_name)
                odds_h, odds_d, odds_a = get_best_odds(fix_id)

            math_probs = calculate_advanced_math_probs(api_goals_h, api_goals_a)
            kelly_h = calculate_kelly_stake(api_h_win/100, odds_h)
            kelly_a = calculate_kelly_stake(api_a_win/100, odds_a)

            cleaned_data.append({
                '時間': t_str, '聯賽': lg_name, '主隊': h_name, '客隊': a_name,
                '狀態': status, '主分': score_h_display, '客分': score_a_display,
                
                '主勝率': api_h_win, '和局率': api_draw, '客勝率': api_a_win,
                
                # 亞盤 (Home)
                '主平': math_probs['ah_0_h'], '主0/-0.5': math_probs['ah_m025_h'], 
                '主-0.5/-1': math_probs['ah_m075_h'], '主-1/-1.5': math_probs['ah_m125_h'],
                '主0/+0.5': math_probs['ah_p025_h'], '主+0.5/+1': math_probs['ah_p075_h'], '主+1/+1.5': math_probs['ah_p125_h'],
                
                # 亞盤 (Away)
                '客平': math_probs['ah_0_a'], '客0/-0.5': math_probs['ah_m025_a'], 
                '客-0.5/-1': math_probs['ah_m075_a'], '客-1/-1.5': math_probs['ah_m125_a'],
                '客0/+0.5': math_probs['ah_p025_a'], '客+0.5/+1': math_probs['ah_p075_a'], '客+1/+1.5': math_probs['ah_p125_a'],
                
                # 進球
                'FTS主': math_probs['fts_h'], 'FTS客': math_probs['fts_a'], 'BTTS': math_probs['btts'],
                'HT0.5': math_probs['ht_o05'], 'HT1.5': math_probs['ht_o15'], 'HT2.5': math_probs['ht_o25'],

                '主賠': odds_h, '客賠': odds_a, '凱利主': round(kelly_h), '凱利客': round(kelly_a),
                '推介': advice, '信心': confidence_score,
                '主狀態': form_h, '客狀態': form_a, '主攻': att_h, '客攻': att_a, '主防': def_h, '客防': def_a, '主傷': inj_h, '客傷': inj_a
            })
            print(f"         ✅ {h_name} vs {a_name}")

    if cleaned_data:
        df = pd.DataFrame(cleaned_data)
        # 更新欄位順序以包含新數據
        cols = ['時間','聯賽','主隊','客隊','狀態','主分','客分',
                '主勝率','和局率','客勝率',
                '主平','主0/-0.5','主-0.5/-1','主-1/-1.5','主0/+0.5','主+0.5/+1','主+1/+1.5',
                '客平','客0/-0.5','客-0.5/-1','客-1/-1.5','客0/+0.5','客+0.5/+1','客+1/+1.5',
                'FTS主','FTS客','BTTS',
                'HT0.5','HT1.5','HT2.5',
                '主賠','客賠','凱利主','凱利客','推介','信心',
                '主狀態','客狀態','主攻','客攻','主防','客防','主傷','客傷']
        
        for c in cols:
            if c not in df.columns: df[c] = 0
            
        df = df.reindex(columns=cols, fill_value='')
        
        spreadsheet = get_google_spreadsheet()
        if spreadsheet:
            try: 
                spreadsheet.sheet1.clear()
                spreadsheet.sheet1.update(range_name='A1', values=[df.columns.values.tolist()] + df.astype(str).values.tolist())
                print("✅ 數據上傳成功！")
            except Exception as e: print(f"❌ 上傳失敗: {e}")
    else:
        print("⚠️ 無數據")

if __name__ == "__main__":
    main()
