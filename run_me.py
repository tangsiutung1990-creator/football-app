import requests
import pandas as pd
import time
import math
import gspread
from datetime import datetime, timedelta
import pytz
from oauth2client.service_account import ServiceAccountCredentials
import numpy as np

# ================= 設定區 (已更新 API-Football) =================
# 你提供的 API Key
API_KEY = '6bf59594223b07234f75a8e2e2de5178' 
BASE_URL = 'https://v3.football.api-sports.io'

# Google Sheet 設定
GOOGLE_SHEET_NAME = "數據上傳" 
MANUAL_TAB_NAME = "球隊身價表" 

# 參數設定
MARKET_GOAL_INFLATION = 1.25 
DIXON_COLES_RHO = -0.13 
CONFIDENCE_INTERVAL_SIGMA = 0.95 

# 聯賽 ID 對照表 (API-Football ID -> 你的代碼代號)
# 39:英超, 140:西甲, 135:意甲, 78:德甲, 61:法甲
LEAGUE_ID_MAP = {
    39: 'PL',
    140: 'PD',
    135: 'SA',
    78: 'BL1',
    61: 'FL1'
}

# 聯賽入球系數
LEAGUE_GOAL_FACTOR = {
    'BL1': 1.45, 'PL': 1.25, 'PD': 1.05,
    'SA': 1.15, 'FL1': 1.10
}

# 豪門名單 (用於調整權重)
TITAN_TEAMS = [
    'Manchester City', 'Liverpool', 'Arsenal', 'Real Madrid', 'Barcelona', 
    'Atletico Madrid', 'Bayern Munich', 'Bayer Leverkusen', 'Dortmund', 
    'Paris Saint Germain', 'Inter', 'Juventus', 'AC Milan', 'Napoli', 
    'Benfica', 'Porto', 'Sporting CP'
]

# ================= API 連接函式 (API-Football 專用) =================
def call_api(endpoint, params=None):
    headers = {
        'x-rapidapi-host': "v3.football.api-sports.io",
        'x-apisports-key': API_KEY
    }
    url = f"{BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"⚠️ API 錯誤: {response.status_code} | {response.text}")
            return None
    except Exception as e:
        print(f"❌ 連線異常: {e}")
        return None

# ================= Google Sheet 連接 =================
def get_google_spreadsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        client = gspread.authorize(creds)
        return client.open(GOOGLE_SHEET_NAME)
    except Exception as e:
        print(f"❌ Google Sheet 連線失敗: {e}")
        print("提示: 請確保 'key.json' 檔案存在且名稱正確。")
        return None

def load_manual_market_values(spreadsheet):
    if not spreadsheet: return {}
    print(f"📖 讀取 '{MANUAL_TAB_NAME}'...")
    market_value_map = {}
    try:
        worksheet = spreadsheet.worksheet(MANUAL_TAB_NAME)
        records = worksheet.get_all_records()
        for row in records:
            team = str(row.get('球隊名稱', '')).strip()
            val = str(row.get('身價', '')).strip()
            if team and val: market_value_map[team] = val
        return market_value_map
    except: return {}

def parse_market_value(val_str):
    if not val_str or val_str == 'N/A': return 0
    try:
        clean = str(val_str).replace('€', '').replace('M', '').replace(',', '').strip()
        return float(clean)
    except: return 0

# ================= 核心計算 (數學模型) =================
def calculate_synthetic_xg(home_exp, away_exp):
    return round(home_exp, 2), round(away_exp, 2)

def calculate_kelly_stake(prob, odds):
    if odds <= 1: return 0
    b = odds - 1
    q = 1 - prob
    f = (b * prob - q) / b
    return max(0, f * 100) 

def calculate_dominance_index(h_info, a_info):
    h_force = (h_info['home_att'] * 1.1) / max(a_info['away_def'], 0.5)
    a_force = (a_info['away_att'] * 1.1) / max(h_info['home_def'], 0.5)
    dom_idx = h_force - a_force
    return round(dom_idx, 2)

def calculate_corner_probs(match_vol, dom_idx):
    lambda_corners = 9.5
    if match_vol > 3.0: lambda_corners += 1.5
    elif match_vol < 2.2: lambda_corners -= 1.0
    if abs(dom_idx) > 1.2: lambda_corners += 1.2
    
    def poisson_cdf(k, lam):
        sum_p = 0
        for i in range(k + 1):
            sum_p += (lam**i * math.exp(-lam)) / math.factorial(i)
        return sum_p

    p75 = 1 - poisson_cdf(7, lambda_corners)
    p85 = 1 - poisson_cdf(8, lambda_corners)
    p95 = 1 - poisson_cdf(9, lambda_corners)
    return round(p75*100), round(p85*100), round(p95*100), round(lambda_corners, 1)

def calculate_handicap_with_prob(h_win, a_win, ah05, ah1, ah2):
    handicap = "0"
    prob = 0
    if h_win > 0.65: handicap = "-1.5"; prob = (ah1 + ah2) / 2 
    elif h_win > 0.6: handicap = "-1.0"; prob = ah1
    elif h_win > 0.55: handicap = "-0.5/1"; prob = (ah05 + ah1) / 2
    elif h_win > 0.45: handicap = "-0.5"; prob = ah05
    elif h_win > 0.4: handicap = "-0/0.5"; prob = h_win + 0.1 
    elif a_win > 0.6: handicap = "客 -1.0"; prob = a_win * 0.85 
    elif a_win > 0.45: handicap = "客 -0.5"; prob = a_win
    elif a_win > 0.4: handicap = "客 -0/0.5"; prob = a_win + 0.1
    return f"{handicap} ({int(prob*100)}%)"

def analyze_team_tags(h_info, a_info, match_vol, h2h_avg_goals, kelly_h, kelly_a, dom_idx, prob_o25):
    tags = []
    h_form = str(h_info.get('form', 'N/A'))
    if dom_idx > 1.2: tags.append("👑主宰")
    elif dom_idx < -1.2: tags.append("👑客宰")
    if h_info['home_att'] > 2.2: tags.append("🏠龍")
    if a_info['away_def'] > 2.0: tags.append("🚌蟲")
    if match_vol > 3.5 and prob_o25 > 0.60: tags.append("🎆大")
    elif match_vol < 2.0 and prob_o25 < 0.40: tags.append("💤細")
    if 'WWWW' in h_form: tags.append("🔥連勝")
    if kelly_h > 10: tags.append("💎主EV")
    if kelly_a > 10: tags.append("💎客EV")
    return " ".join(tags) if tags else "⚖️均"

def calculate_alpha_pick(h_win, a_win, prob_o25, prob_btts, h2h_avg, match_vol, kelly_h, kelly_a, dom_idx):
    scores = {}
    if prob_o25 > 0.50: scores['2.5大'] = prob_o25 * 100 + (10 if h2h_avg > 3.0 else 0)
    else: scores['2.5大'] = -999 
    if (1 - prob_o25) > 0.50: scores['2.5細'] = (1 - prob_o25) * 100 + (10 if match_vol < 2.2 else 0)
    else: scores['2.5細'] = -999
    if h_win > 0.40: scores['主勝'] = h_win * 100 + kelly_h
    else: scores['主勝'] = -999
    if a_win > 0.40: scores['客勝'] = a_win * 100 + kelly_a
    else: scores['客勝'] = -999
    if prob_btts > 0.55: scores['BTTS'] = prob_btts * 100
    else: scores['BTTS'] = -999
    
    valid_scores = {k: v for k, v in scores.items() if v > 0}
    if not valid_scores: return "觀望", 0
    best_pick = max(valid_scores, key=valid_scores.get)
    best_score = valid_scores[best_pick]
    
    rating = ""
    if best_score > 90: rating = "🌟"
    elif best_score > 75: rating = "🔥"
    elif best_score > 60: rating = "✅"
    else: rating = "🤔" 
    return f"{best_pick} {rating}", best_score

def calculate_risk_level(ou_conf, match_vol, prob_o25, kelly_sum, range_spread):
    score = 50 - (ou_conf - 50)
    if range_spread > 1.5: score += 20 
    if prob_o25 < 0.45 and prob_o25 > 0.35: score += 15 
    if prob_o25 > 0.7 or prob_o25 < 0.3: score -= 20
    if kelly_sum > 20: score -= 15 
    if score < 30: return "🟢極穩"
    elif score < 55: return "🔵穩健"
    else: return "🔴高險"

def calculate_advanced_probs(home_exp, away_exp, h2h_o25_rate, match_vol, h2h_avg_goals):
    def poisson(k, lam): return (lam**k * math.exp(-lam)) / math.factorial(k)
    def adjustment(x, y, lam, mu, rho):
        if x == 0 and y == 0: return 1 - (lam * mu * rho)
        if x == 0 and y == 1: return 1 + (lam * rho)
        if x == 1 and y == 0: return 1 + (mu * rho)
        if x == 1 and y == 1: return 1 - rho
        return 1.0

    h_win=0; draw=0; a_win=0
    prob_o15 = 0; prob_o25 = 0; prob_o35 = 0
    ah_minus_05 = 0; ah_minus_1 = 0; ah_minus_2 = 0
    ht_lambda_h = home_exp * 0.45 
    ht_lambda_a = away_exp * 0.45
    ht_h_win = 0; ht_draw = 0; ht_a_win = 0
    
    total_exp = home_exp + away_exp
    std_dev = math.sqrt(total_exp)
    lower_bound = max(0, total_exp - CONFIDENCE_INTERVAL_SIGMA * std_dev)
    upper_bound = total_exp + CONFIDENCE_INTERVAL_SIGMA * std_dev
    
    for h in range(15): 
        for a in range(15):
            base_prob = poisson(h, home_exp) * poisson(a, away_exp)
            adj = adjustment(h, a, home_exp, away_exp, DIXON_COLES_RHO)
            final_prob = max(0, base_prob * adj)
            
            if h > a: 
                h_win += final_prob; ah_minus_05 += final_prob
            elif h == a: draw += final_prob
            else: a_win += final_prob
            
            if (h - a) >= 2: ah_minus_1 += final_prob 
            if (h - a) >= 3: ah_minus_2 += final_prob
            
            total = h + a
            if total > 1.5: prob_o15 += final_prob
            if total > 2.5: prob_o25 += final_prob
            if total > 3.5: prob_o35 += final_prob

    for h in range(7):
        for a in range(7):
            p = poisson(h, ht_lambda_h) * poisson(a, ht_lambda_a)
            if h > a: ht_h_win += p
            elif h == a: ht_draw += p
            else: ht_a_win += p

    total_prob = h_win + draw + a_win
    if total_prob > 0:
        h_win/=total_prob; draw/=total_prob; a_win/=total_prob
        prob_o15/=total_prob; prob_o25/=total_prob; prob_o35/=total_prob
        ah_minus_05/=total_prob; ah_minus_1/=total_prob; ah_minus_2/=total_prob

    prob_ht_o05 = 1 - (poisson(0, ht_lambda_h) * poisson(0, ht_lambda_a))
    btts = (1 - poisson(0, home_exp)) * (1 - poisson(0, away_exp))
    
    limit = 50.0
    fair_1x2_h = min((1 / max(h_win, 0.01)), limit)
    fair_1x2_d = min((1 / max(draw, 0.01)), limit)
    fair_1x2_a = min((1 / max(a_win, 0.01)), limit)
    fair_o25 = min((1 / max(prob_o25, 0.01)), limit)
    
    safety_margin = 1.05
    min_odds_h = round(fair_1x2_h * safety_margin, 2)
    min_odds_a = round(fair_1x2_a * safety_margin, 2)
    min_odds_o25 = round(fair_o25 * safety_margin, 2)

    market_sim_h = fair_1x2_h * 0.95 
    kelly_h = calculate_kelly_stake(h_win, market_sim_h * 1.15) 
    kelly_a = calculate_kelly_stake(a_win, fair_1x2_a * 1.05) 

    math_conf = abs(prob_o25 - 0.5) * 2 * 40
    vol_conf = 25 if (prob_o25 > 0.5 and match_vol > 3.2) or (prob_o25 < 0.5 and match_vol < 2.2) else 0
    total_conf = max(min(math_conf + vol_conf, 99), 25) 
    
    live_strat = "中性"
    if match_vol > 3.1: live_strat = "🔥追大"
    elif match_vol < 2.3: live_strat = "🛡️細/角"
    elif home_exp > away_exp * 2: live_strat = "🏰主控"
    if prob_ht_o05 > 0.72: live_strat += "|HT大"
    
    return {
        'btts': round(btts*100, 1), 
        'h_win': h_win, 'draw': draw, 'a_win': a_win,
        'ht_h_win': ht_h_win, 'ht_draw': ht_draw, 'ht_a_win': ht_a_win,
        'ah_minus_05': round(ah_minus_05*100, 1),
        'ah_minus_1': round(ah_minus_1*100, 1),
        'ah_minus_2': round(ah_minus_2*100, 1),
        'prob_o15': round(prob_o15*100, 1), 
        'prob_o25': round(prob_o25*100, 1),
        'prob_o35': round(prob_o35*100, 1), 
        'prob_ht_o05': round(prob_ht_o05*100, 1), 
        'ou_conf': round(total_conf, 1),
        'fair_1x2_h': round(fair_1x2_h, 2),
        'fair_1x2_d': round(fair_1x2_d, 2),
        'fair_1x2_a': round(fair_1x2_a, 2),
        'min_odds_h': min_odds_h, 
        'min_odds_a': min_odds_a,
        'min_odds_o25': min_odds_o25,
        'fair_o25': round(fair_o25, 2),
        'live_strat': live_strat,
        'kelly_h': round(kelly_h, 1),
        'kelly_a': round(kelly_a, 1),
        'goal_range_low': round(lower_bound, 1), 
        'goal_range_high': round(upper_bound, 1) 
    }

def calculate_correct_score_probs(home_exp, away_exp):
    def poisson(k, lam): return (lam**k * math.exp(-lam)) / math.factorial(k)
    scores = []
    for h in range(7):
        for a in range(7):
            prob = poisson(h, home_exp) * poisson(a, away_exp)
            if h==0 and a==0: prob *= (1 - home_exp*away_exp*DIXON_COLES_RHO)
            elif h==1 and a==1: prob *= (1 - DIXON_COLES_RHO)
            scores.append({'score': f"{h}:{a}", 'prob': prob})
    scores.sort(key=lambda x: x['prob'], reverse=True)
    top_3 = [f"{s['score']} ({int(s['prob']*100)}%)" for s in scores[:3]]
    return " | ".join(top_3)

def calculate_weighted_form_score(form_str):
    if not form_str or form_str == 'N/A': return 1.5 
    score = 0; total_weight = 0
    relevant = str(form_str).replace(',', '').strip()[-5:]
    weights = [1.0, 1.2, 1.4, 1.8, 2.2] 
    start_idx = 5 - len(relevant)
    curr_weights = weights[start_idx:]
    for i, char in enumerate(relevant):
        w = curr_weights[i]
        s = 3 if char.upper()=='W' else 1 if char.upper()=='D' else 0
        score += s * w
        total_weight += w
    return score / total_weight if total_weight > 0 else 1.5

def predict_match_outcome(h_name, h_info, a_info, h_val_str, a_val_str, h2h_o25_rate, h2h_avg_goals, league_avg, lg_code):
    lg_h = league_avg.get('avg_home', 1.6)
    lg_a = league_avg.get('avg_away', 1.3)
    
    factor = LEAGUE_GOAL_FACTOR.get(lg_code, 1.1) * MARKET_GOAL_INFLATION
    
    h_att_r = (h_info['home_att'] / lg_h) * 1.05
    a_def_r = (a_info['away_def'] / lg_h) * 1.05
    h_strength = (h_att_r * a_def_r) ** 1.3
    
    a_att_r = (a_info['away_att'] / lg_a) * 1.05
    h_def_r = (h_info['home_def'] / lg_a) * 1.05
    a_strength = (a_att_r * h_def_r) ** 1.3 

    raw_h = h_strength * lg_h * factor
    raw_a = a_strength * lg_a * factor
    
    h_v = parse_market_value(h_val_str); a_v = parse_market_value(a_val_str)
    
    if h_v > 0 and a_v > 0:
        ratio = h_v / a_v
        if ratio > 8.0: raw_h *= 1.45; raw_a *= 0.7
        elif ratio > 4.0: raw_h *= 1.25; raw_a *= 0.85
        val_factor = max(min(math.log(ratio) * 0.2, 0.5), -0.5)
        raw_h *= (1 + val_factor); raw_a *= (1 - val_factor)

    h_vol = h_info.get('volatility', 2.5)
    a_vol = a_info.get('volatility', 2.5)
    match_vol = (h_vol + a_vol) / 2
    
    if match_vol > 3.4: raw_h *= 1.25; raw_a *= 1.25
    elif match_vol > 3.0: raw_h *= 1.15; raw_a *= 1.15
    elif match_vol < 2.2: raw_h *= 0.85; raw_a *= 0.85

    if h2h_avg_goals != -1:
        if h2h_avg_goals >= 3.5: raw_h *= 1.2; raw_a *= 1.2
        elif h2h_avg_goals >= 3.0: raw_h *= 1.1; raw_a *= 1.1
        elif h2h_avg_goals <= 1.5: raw_h *= 0.85; raw_a *= 0.85

    h_mom = calculate_weighted_form_score(h_info['form']) - h_info['season_ppg']
    a_mom = calculate_weighted_form_score(a_info['form']) - a_info['season_ppg']
    raw_h *= (1 + (h_mom * 0.15)) 
    raw_a *= (1 + (a_mom * 0.15))
    
    if raw_h < 0.25: raw_h = 0.25
    if raw_a < 0.25: raw_a = 0.25

    return round(raw_h, 2), round(raw_a, 2), round(match_vol, 2), round(h_mom, 2), round(a_mom, 2)

# ================= 數據抓取主流程 =================
def get_standings_from_new_api():
    print("📊 [API-Football] 正在下載各聯賽積分榜...")
    standings_map = {}
    league_stats = {} 

    # 使用 2024 賽季 (API-Football v3)
    current_season = 2024

    for lg_id, lg_code in LEAGUE_ID_MAP.items():
        params = {'league': lg_id, 'season': current_season}
        data = call_api('standings', params=params)
        
        if not data or not data.get('response'):
            print(f"   ⚠️ 無法獲取聯賽 ID {lg_id} 的數據")
            continue

        league_total_home_goals = 0
        league_total_matches = 0
        
        try:
            standings_data = data['response'][0]['league']['standings'][0]
            for row in standings_data:
                team_name = row['team']['name']
                played = row['all']['played']
                points = row['points']
                form = row['form'] # 格式如 "WWLDW"
                
                h_played = row['home']['played']
                h_for = row['home']['goals']['for']
                h_against = row['home']['goals']['against']
                
                a_played = row['away']['played']
                a_for = row['away']['goals']['for']
                a_against = row['away']['goals']['against']

                avg_h_att = h_for / h_played if h_played > 0 else 1.3
                avg_h_def = h_against / h_played if h_played > 0 else 1.3
                avg_a_att = a_for / a_played if a_played > 0 else 1.0
                avg_a_def = a_against / a_played if a_played > 0 else 1.0
                
                volatility = (row['all']['goals']['for'] + row['all']['goals']['against']) / played if played > 0 else 2.5
                ppg = points / played if played > 0 else 1.0

                standings_map[team_name] = {
                    'rank': row['rank'],
                    'form': form,
                    'home_att': avg_h_att,
                    'home_def': avg_h_def,
                    'away_att': avg_a_att,
                    'away_def': avg_a_def,
                    'season_ppg': ppg,
                    'volatility': volatility
                }
                
                league_total_home_goals += h_for
                league_total_matches += h_played
            
            avg_home = league_total_home_goals / league_total_matches if league_total_matches > 0 else 1.5
            league_stats[lg_code] = {'avg_home': avg_home, 'avg_away': avg_home * 0.85}
            print(f"   ✅ 成功讀取: {lg_code}")

        except Exception as e:
            print(f"   ❌ 解析聯賽 {lg_code} 出錯: {e}")
            
    return standings_map, league_stats

def get_fixtures_and_analyze(standings_map, league_stats, market_value_map):
    print("🚀 [API-Football] 正在獲取賽程...")
    cleaned = []
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    
    utc_now = datetime.now(pytz.utc)
    # 搜尋範圍：昨天 到 未來3天
    from_date = (utc_now - timedelta(days=1)).strftime('%Y-%m-%d')
    to_date = (utc_now + timedelta(days=3)).strftime('%Y-%m-%d')
    
    current_season = 2024 
    
    # 修正：逐個聯賽查詢
    for lg_id, lg_code in LEAGUE_ID_MAP.items():
        params = {
            'league': lg_id, 
            'season': current_season,
            'from': from_date, 
            'to': to_date
        }
        
        print(f"   🔍 查詢 {lg_code} ({from_date} to {to_date})...")
        data = call_api('fixtures', params=params)
        
        if not data or not data.get('response'):
            continue

        fixtures = data['response']
        
        for item in fixtures:
            fixture = item['fixture']
            teams = item['teams']
            goals = item['goals']
            
            # 時間轉換
            utc_dt = datetime.fromtimestamp(fixture['timestamp'], pytz.utc)
            time_str = utc_dt.astimezone(hk_tz).strftime('%Y-%m-%d %H:%M')
            
            # 狀態
            status_short = fixture['status']['short']
            status = '未開賽'
            if status_short in ['1H','2H','HT','ET','P','LIVE']: status = '進行中'
            elif status_short in ['FT','AET','PEN']: status = '完場'
            elif status_short in ['PST', 'CANC', 'ABD']: status = '延期/取消'

            h_name = teams['home']['name']
            a_name = teams['away']['name']
            
            # 獲取球隊數據
            h_info = standings_map.get(h_name, {'rank':10,'form':'N/A','home_att':1.3,'home_def':1.3,'volatility':2.5,'season_ppg':1.3})
            a_info = standings_map.get(a_name, {'rank':10,'form':'N/A','away_att':1.1,'away_def':1.1,'volatility':2.5,'season_ppg':1.3})
            
            # 身價
            h_val = market_value_map.get(h_name, "N/A")
            a_val = market_value_map.get(a_name, "N/A")
            
            # H2H (節省 API，暫時設為中性)
            h2h_str = "N/A"; h2h_avg = -1; h2h_o25_rate = 0.5
            
            # 預測
            lg_avg = league_stats.get(lg_code, {'avg_home': 1.6, 'avg_away': 1.3})
            pred_h, pred_a, vol, h_mom, a_mom = predict_match_outcome(
                h_name, h_info, a_info, h_val, a_val, h2h_o25_rate, h2h_avg, lg_avg, lg_code
            )
            
            xg_h, xg_a = calculate_synthetic_xg(pred_h, pred_a)
            correct_score_str = calculate_correct_score_probs(pred_h, pred_a)
            adv_stats = calculate_advanced_probs(pred_h, pred_a, h2h_o25_rate, vol, h2h_avg)
            dom_idx = calculate_dominance_index(h_info, a_info)
            c75, c85, c95, c_exp = calculate_corner_probs(vol, dom_idx)
            handicap_txt = calculate_handicap_with_prob(adv_stats['h_win'], adv_stats['a_win'], adv_stats['ah_minus_05'], adv_stats['ah_minus_1'], adv_stats['ah_minus_2'])
            kelly_sum = adv_stats['kelly_h'] + adv_stats['kelly_a']
            smart_tags = analyze_team_tags(h_info, a_info, vol, h2h_avg, adv_stats['kelly_h'], adv_stats['kelly_a'], dom_idx, adv_stats['prob_o25'])
            risk_level = calculate_risk_level(adv_stats['ou_conf'], vol, adv_stats['prob_o25'], kelly_sum, (adv_stats['goal_range_high'] - adv_stats['goal_range_low']))
            
            top_pick, pick_score = calculate_alpha_pick(
                adv_stats['h_win'], adv_stats['a_win'], 
                adv_stats['prob_o25'], adv_stats['btts']/100, 
                h2h_avg, vol, adv_stats['kelly_h'], adv_stats['kelly_a'], dom_idx
            )

            score_h = goals['home'] if goals['home'] is not None else ''
            score_a = goals['away'] if goals['away'] is not None else ''

            print(f"   👉 分析: {h_name} vs {a_name} | {top_pick}")

            cleaned.append({
                '時間': time_str, '聯賽': lg_code,
                '主隊': h_name, '客隊': a_name,
                '主排名': h_info['rank'], '客排名': a_info['rank'],
                '主近況': h_info['form'], '客近況': a_info['form'],
                '主預測': pred_h, '客預測': pred_a,
                'xG主': xg_h, 'xG客': xg_a, 
                '總球數': round(pred_h + pred_a, 1),
                '狀態': status, '主分': score_h, '客分': score_a,
                'H2H': h2h_str, 'H2H平均球': h2h_avg,
                '主隊身價': h_val, '客隊身價': a_val,
                '主導指數': dom_idx,
                '波膽預測': correct_score_str,
                'BTTS': adv_stats['btts'],
                '主勝率': round(adv_stats['h_win']*100),
                '和局率': round(adv_stats['draw']*100),
                '客勝率': round(adv_stats['a_win']*100),
                'HT主': round(adv_stats['ht_h_win']*100),
                'HT和': round(adv_stats['ht_draw']*100),
                'HT客': round(adv_stats['ht_a_win']*100),
                'AH-0.5': round(adv_stats['ah_minus_05']*100),
                'AH-1.0': round(adv_stats['ah_minus_1']*100),
                'AH-2.0': round(adv_stats['ah_minus_2']*100),
                'C75': c75, 'C85': c85, 'C95': c95,
                '大球率1.5': adv_stats['prob_o15'],
                '大球率2.5': adv_stats['prob_o25'],
                '大球率3.5': adv_stats['prob_o35'],
                '合理主賠': adv_stats['fair_1x2_h'],
                '合理和賠': adv_stats['fair_1x2_d'],
                '合理客賠': adv_stats['fair_1x2_a'],
                '最低賠率主': adv_stats['min_odds_h'], 
                '最低賠率客': adv_stats['min_odds_a'], 
                '最低賠率大2.5': adv_stats['min_odds_o25'], 
                '合理大賠2.5': adv_stats['fair_o25'], 
                '凱利主(%)': adv_stats['kelly_h'],
                '凱利客(%)': adv_stats['kelly_a'],
                '亞盤建議': handicap_txt, 
                '角球預測': f"{c_exp}", 
                '入球區間低': adv_stats['goal_range_low'],
                '入球區間高': adv_stats['goal_range_high'],
                '走地策略': adv_stats['live_strat'],
                '智能標籤': smart_tags,
                '風險評級': risk_level,
                '首選推介': top_pick
            })
    return cleaned

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 V16.1 API-Football (Fixed) 啟動...")
    
    # 1. 連接 Google Sheet
    spreadsheet = get_google_spreadsheet()
    market_value_map = load_manual_market_values(spreadsheet) if spreadsheet else {}
    
    # 2. 獲取新數據 (Standings)
    standings, league_stats = get_standings_from_new_api()
    
    # 3. 獲取賽程並分析
    if standings:
        real_data = get_fixtures_and_analyze(standings, league_stats, market_value_map)
        
        if real_data:
            df = pd.DataFrame(real_data)
            # 確保列順序
            cols = ['時間','聯賽','主隊','客隊','主排名','客排名','主近況','客近況','主預測','客預測',
                    'xG主','xG客','主勝率','和局率','客勝率','HT主','HT和','HT客',
                    'AH-0.5','AH-1.0','AH-2.0','C75','C85','C95',
                    '總球數','狀態','主分','客分','H2H','H2H平均球',
                    '主隊身價','客隊身價','主導指數','波膽預測',
                    'BTTS','大球率1.5','大球率2.5','大球率3.5',
                    '合理主賠','合理和賠','合理客賠','最低賠率主','最低賠率客',
                    '最低賠率大2.5','合理大賠2.5','亞盤建議','角球預測',
                    '凱利主(%)','凱利客(%)','入球區間低','入球區間高',
                    '走地策略','智能標籤','風險評級','首選推介']
            df = df.reindex(columns=cols, fill_value='')
            
            if spreadsheet:
                try:
                    upload_sheet = spreadsheet.sheet1 
                    upload_sheet.clear() 
                    upload_sheet.update(range_name='A1', values=[df.columns.values.tolist()] + df.astype(str).values.tolist())
                    print(f"✅ 上傳完成！共 {len(real_data)} 場賽事。")
                except Exception as e: print(f"❌ 上傳失敗: {e}")
        else:
            print("⚠️ 未找到這幾天的比賽數據 (可能是淡季或聯賽無賽事)。")
    else:
        print("⚠️ 無法獲取積分榜數據，程序終止。")

if __name__ == "__main__":
    main()
