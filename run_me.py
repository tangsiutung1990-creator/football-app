import requests
import pandas as pd
import math
import gspread
from datetime import datetime, timedelta
import pytz
from oauth2client.service_account import ServiceAccountCredentials

# ================= 設定區 =================
API_KEY = '6bf59594223b07234f75a8e2e2de5178' 
BASE_URL = 'https://v3.football.api-sports.io'
GOOGLE_SHEET_NAME = "數據上傳" 
MANUAL_TAB_NAME = "球隊身價表" 

# 參數設定
MARKET_GOAL_INFLATION = 1.25 
DIXON_COLES_RHO = -0.13 
CONFIDENCE_INTERVAL_SIGMA = 0.95 

# 聯賽 ID 對照表
LEAGUE_ID_MAP = {
    39: 'PL',    # 英超
    140: 'PD',   # 西甲
    135: 'SA',   # 意甲
    78: 'BL1',   # 德甲
    61: 'FL1'    # 法甲
}

LEAGUE_GOAL_FACTOR = {
    'BL1': 1.45, 'PL': 1.25, 'PD': 1.05, 'SA': 1.15, 'FL1': 1.10
}

# ================= API 連接函式 =================
def call_api(endpoint, params=None):
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-apisports-key': API_KEY}
    url = f"{BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200: return response.json()
        else: print(f"⚠️ API Error: {response.status_code}"); return None
    except Exception as e: print(f"❌ Connection Error: {e}"); return None

# ================= Google Sheet 連接 =================
def get_google_spreadsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        client = gspread.authorize(creds)
        return client.open(GOOGLE_SHEET_NAME)
    except: return None

def load_manual_market_values(spreadsheet):
    if not spreadsheet: return {}
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
    try: return float(str(val_str).replace('€', '').replace('M', '').replace(',', '').strip())
    except: return 0

# ================= 核心計算 (數學模型) =================
def calculate_synthetic_xg(home_exp, away_exp):
    return round(home_exp, 2), round(away_exp, 2)

def calculate_kelly_stake(prob, odds):
    if odds <= 1: return 0
    b = odds - 1; q = 1 - prob; f = (b * prob - q) / b
    return max(0, f * 100) 

def calculate_dominance_index(h_info, a_info):
    h_force = (h_info['home_att'] * 1.1) / max(a_info['away_def'], 0.5)
    a_force = (a_info['away_att'] * 1.1) / max(h_info['home_def'], 0.5)
    return round(h_force - a_force, 2)

def calculate_corner_probs(match_vol, dom_idx):
    lambda_corners = 9.5
    if match_vol > 3.0: lambda_corners += 1.5
    elif match_vol < 2.2: lambda_corners -= 1.0
    if abs(dom_idx) > 1.2: lambda_corners += 1.2
    def poisson_cdf(k, lam):
        sum_p = 0
        for i in range(k + 1): sum_p += (lam**i * math.exp(-lam)) / math.factorial(i)
        return sum_p
    return round((1-poisson_cdf(7, lambda_corners))*100), round((1-poisson_cdf(8, lambda_corners))*100), round((1-poisson_cdf(9, lambda_corners))*100), round(lambda_corners, 1)

def calculate_handicap_with_prob(h_win, a_win, ah05, ah1, ah2):
    if h_win > 0.65: return f"-1.5 ({int((ah1+ah2)/2*100)}%)"
    elif h_win > 0.6: return f"-1.0 ({int(ah1*100)}%)"
    elif h_win > 0.55: return f"-0.5/1 ({int((ah05+ah1)/2*100)}%)"
    elif h_win > 0.45: return f"-0.5 ({int(ah05*100)}%)"
    elif h_win > 0.4: return f"-0/0.5 ({int((h_win+0.1)*100)}%)"
    elif a_win > 0.6: return f"客 -1.0 ({int(a_win*0.85*100)}%)"
    elif a_win > 0.45: return f"客 -0.5 ({int(a_win*100)}%)"
    elif a_win > 0.4: return f"客 -0/0.5 ({int((a_win+0.1)*100)}%)"
    return "0"

def analyze_team_tags(h_info, a_info, match_vol, h2h_avg_goals, kelly_h, kelly_a, dom_idx, prob_o25):
    tags = []
    if dom_idx > 1.2: tags.append("👑主宰")
    elif dom_idx < -1.2: tags.append("👑客宰")
    if h_info['home_att'] > 2.2: tags.append("🏠龍")
    if a_info['away_def'] > 2.0: tags.append("🚌蟲")
    if match_vol > 3.5 and prob_o25 > 0.60: tags.append("🎆大")
    elif match_vol < 2.0 and prob_o25 < 0.40: tags.append("💤細")
    if 'WWWW' in str(h_info.get('form')): tags.append("🔥連勝")
    if kelly_h > 10: tags.append("💎主EV")
    if kelly_a > 10: tags.append("💎客EV")
    return " ".join(tags) if tags else "⚖️均"

def calculate_alpha_pick(h_win, a_win, prob_o25, prob_btts, h2h_avg, match_vol, kelly_h, kelly_a, dom_idx):
    scores = {}
    scores['2.5大'] = prob_o25 * 100 + (10 if h2h_avg > 3.0 else 0) if prob_o25 > 0.5 else -999
    scores['2.5細'] = (1-prob_o25) * 100 + (10 if match_vol < 2.2 else 0) if (1-prob_o25) > 0.5 else -999
    scores['主勝'] = h_win * 100 + kelly_h if h_win > 0.4 else -999
    scores['客勝'] = a_win * 100 + kelly_a if a_win > 0.4 else -999
    scores['BTTS'] = prob_btts * 100 if prob_btts > 0.55 else -999
    
    valid_scores = {k: v for k, v in scores.items() if v > 0}
    if not valid_scores: return "觀望", 0
    best = max(valid_scores, key=valid_scores.get)
    sc = valid_scores[best]
    return f"{best} {'🌟' if sc>90 else '🔥' if sc>75 else '✅'}", sc

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

    h_win=0; draw=0; a_win=0; prob_o15=0; prob_o25=0; prob_o35=0
    ah_minus_05=0; ah_minus_1=0; ah_minus_2=0
    ht_lambda_h = home_exp * 0.45; ht_lambda_a = away_exp * 0.45
    ht_h_win=0; ht_draw=0; ht_a_win=0
    
    total_exp = home_exp + away_exp
    std_dev = math.sqrt(total_exp)
    lower_bound = max(0, total_exp - CONFIDENCE_INTERVAL_SIGMA * std_dev)
    upper_bound = total_exp + CONFIDENCE_INTERVAL_SIGMA * std_dev
    
    for h in range(10): 
        for a in range(10):
            base_prob = poisson(h, home_exp) * poisson(a, away_exp)
            adj = adjustment(h, a, home_exp, away_exp, DIXON_COLES_RHO)
            final_prob = max(0, base_prob * adj)
            
            if h > a: h_win += final_prob; ah_minus_05 += final_prob
            elif h == a: draw += final_prob
            else: a_win += final_prob
            
            if (h - a) >= 2: ah_minus_1 += final_prob 
            if (h - a) >= 3: ah_minus_2 += final_prob
            
            if h+a > 1.5: prob_o15 += final_prob
            if h+a > 2.5: prob_o25 += final_prob
            if h+a > 3.5: prob_o35 += final_prob

    for h in range(6):
        for a in range(6):
            p = poisson(h, ht_lambda_h) * poisson(a, ht_lambda_a)
            if h > a: ht_h_win += p
            elif h == a: ht_draw += p
            else: ht_a_win += p

    total = h_win + draw + a_win
    if total > 0:
        h_win/=total; draw/=total; a_win/=total
        prob_o15/=total; prob_o25/=total; prob_o35/=total
        ah_minus_05/=total; ah_minus_1/=total; ah_minus_2/=total

    prob_ht_o05 = 1 - (poisson(0, ht_lambda_h) * poisson(0, ht_lambda_a))
    btts = (1 - poisson(0, home_exp)) * (1 - poisson(0, away_exp))
    
    limit = 50.0
    fair_1x2_h = min((1/max(h_win,0.01)), limit)
    fair_1x2_d = min((1/max(draw,0.01)), limit)
    fair_1x2_a = min((1/max(a_win,0.01)), limit)
    fair_o25 = min((1/max(prob_o25,0.01)), limit)
    
    kelly_h = calculate_kelly_stake(h_win, fair_1x2_h*1.05) 
    kelly_a = calculate_kelly_stake(a_win, fair_1x2_a*1.05) 
    
    math_conf = abs(prob_o25 - 0.5) * 80
    total_conf = max(min(math_conf, 99), 25) 
    
    live_strat = "🔥追大" if match_vol > 3.1 else "🛡️細/角" if match_vol < 2.3 else "🏰主控" if home_exp > away_exp*2 else "中性"
    if prob_ht_o05 > 0.72: live_strat += "|HT大"
    
    return {
        'btts': round(btts*100, 1), 
        'h_win': h_win, 'draw': draw, 'a_win': a_win,
        'ht_h_win': ht_h_win, 'ht_draw': ht_draw, 'ht_a_win': ht_a_win,
        'ah_minus_05': round(ah_minus_05*100, 1), 'ah_minus_1': round(ah_minus_1*100, 1), 'ah_minus_2': round(ah_minus_2*100, 1),
        'prob_o15': round(prob_o15*100, 1), 'prob_o25': round(prob_o25*100, 1), 'prob_o35': round(prob_o35*100, 1), 
        'prob_ht_o05': round(prob_ht_o05*100, 1), 'ou_conf': round(total_conf, 1),
        'fair_1x2_h': round(fair_1x2_h, 2), 'fair_1x2_d': round(fair_1x2_d, 2), 'fair_1x2_a': round(fair_1x2_a, 2),
        'min_odds_h': round(fair_1x2_h*1.05, 2), 'min_odds_a': round(fair_1x2_a*1.05, 2), 'min_odds_o25': round(fair_o25*1.05, 2), 
        'fair_o25': round(fair_o25, 2), 'live_strat': live_strat,
        'kelly_h': round(kelly_h, 1), 'kelly_a': round(kelly_a, 1),
        'goal_range_low': round(lower_bound, 1), 'goal_range_high': round(upper_bound, 1) 
    }

def calculate_correct_score_probs(home_exp, away_exp):
    def poisson(k, lam): return (lam**k * math.exp(-lam)) / math.factorial(k)
    scores = []
    for h in range(6):
        for a in range(6):
            prob = poisson(h, home_exp) * poisson(a, away_exp)
            if h==0 and a==0: prob *= (1 - home_exp*away_exp*DIXON_COLES_RHO)
            scores.append({'score': f"{h}:{a}", 'prob': prob})
    scores.sort(key=lambda x: x['prob'], reverse=True)
    return " | ".join([f"{s['score']} ({int(s['prob']*100)}%)" for s in scores[:3]])

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

def predict_match_outcome(h_name, h_info, a_info, h_val, a_val, h2h_o25_rate, h2h_avg, lg_avg, lg_code):
    lg_h = lg_avg.get('avg_home', 1.6); lg_a = lg_avg.get('avg_away', 1.3)
    factor = LEAGUE_GOAL_FACTOR.get(lg_code, 1.1) * MARKET_GOAL_INFLATION
    
    h_att_r = (h_info['home_att'] / lg_h) * 1.05; a_def_r = (a_info['away_def'] / lg_h) * 1.05
    raw_h = ((h_att_r * a_def_r) ** 1.3) * lg_h * factor
    
    a_att_r = (a_info['away_att'] / lg_a) * 1.05; h_def_r = (h_info['home_def'] / lg_a) * 1.05
    raw_a = ((a_att_r * h_def_r) ** 1.3) * lg_a * factor
    
    if h_val > 0 and a_val > 0:
        ratio = h_val / a_val
        val_factor = max(min(math.log(ratio) * 0.2, 0.5), -0.5)
        raw_h *= (1 + val_factor); raw_a *= (1 - val_factor)

    match_vol = (h_info.get('volatility', 2.5) + a_info.get('volatility', 2.5)) / 2
    if match_vol > 3.0: raw_h *= 1.15; raw_a *= 1.15
    elif match_vol < 2.2: raw_h *= 0.85; raw_a *= 0.85

    h_mom = calculate_weighted_form_score(h_info['form']); a_mom = calculate_weighted_form_score(a_info['form'])
    raw_h *= (1 + (h_mom-1.3)*0.15); raw_a *= (1 + (a_mom-1.3)*0.15)
    
    return round(max(0.2, raw_h), 2), round(max(0.2, raw_a), 2), round(match_vol, 2), round(h_mom, 2), round(a_mom, 2)

# ================= 主流程 =================
def main():
    # ⚠️ 鎖定 2025 賽季 (對應 2026 年初)
    season = 2025
    print(f"📊 [API-Football] 正在下載 {season}-{season+1} 賽季數據 (V16.6 Complete)...")
    
    standings_map = {}; league_stats = {} 
    
    # 1. 獲取積分榜
    for lg_id, lg_code in LEAGUE_ID_MAP.items():
        data = call_api('standings', {'league': lg_id, 'season': season})
        if not data or not data.get('response'):
            print(f"   ⚠️ 無法獲取 {lg_code} 數據 (可能權限不足或未開季)"); continue
            
        l_h_g = 0; l_m = 0
        for row in data['response'][0]['league']['standings'][0]:
            t = row['team']['name']
            p = row['all']['played']
            h_f = row['home']['goals']['for']; h_a = row['home']['goals']['against']
            a_f = row['away']['goals']['for']; a_a = row['away']['goals']['against']
            h_p = row['home']['played']; a_p = row['away']['played']
            
            standings_map[t] = {
                'rank': row['rank'], 'form': row['form'],
                'home_att': h_f/h_p if h_p>0 else 1.3, 'home_def': h_a/h_p if h_p>0 else 1.3,
                'away_att': a_f/a_p if a_p>0 else 1.0, 'away_def': a_a/a_p if a_p>0 else 1.0,
                'volatility': (row['all']['goals']['for'] + row['all']['goals']['against'])/p if p>0 else 2.5
            }
            l_h_g += h_f; l_m += h_p
            
        league_stats[lg_code] = {'avg_home': l_h_g/l_m if l_m>0 else 1.5, 'avg_away': (l_h_g/l_m)*0.85 if l_m>0 else 1.3}
        print(f"   ✅ {lg_code} 數據更新完成")

    # 2. 獲取賽程 (未來 3 日)
    print(f"🚀 [API-Football] 正在掃描未來賽程...")
    
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    utc_now = datetime.now(pytz.utc)
    from_date = (utc_now - timedelta(days=1)).strftime('%Y-%m-%d')
    to_date = (utc_now + timedelta(days=3)).strftime('%Y-%m-%d')
    
    cleaned = []
    
    for lg_id, lg_code in LEAGUE_ID_MAP.items():
        print(f"   🔍 掃描 {lg_code} ({from_date} to {to_date})...")
        data = call_api('fixtures', {'league': lg_id, 'season': season, 'from': from_date, 'to': to_date})
        
        if not data or not data.get('response'): continue
        fixtures = data['response']
        print(f"      👉 找到 {len(fixtures)} 場比賽")
        
        spreadsheet = get_google_spreadsheet()
        market_value_map = load_manual_market_values(spreadsheet)

        for item in fixtures:
            f = item['fixture']; h = item['teams']['home']['name']; a = item['teams']['away']['name']
            t_str = datetime.fromtimestamp(f['timestamp'], pytz.utc).astimezone(hk_tz).strftime('%Y-%m-%d %H:%M')
            status = '進行中' if f['status']['short'] in ['1H','2H','HT','LIVE'] else '未開賽'
            if f['status']['short'] in ['FT','AET','PEN']: status = '完場'

            h_i = standings_map.get(h, {'rank':10,'form':'N/A','home_att':1.3,'home_def':1.3,'volatility':2.5})
            a_i = standings_map.get(a, {'rank':10,'form':'N/A','away_att':1.1,'away_def':1.1,'volatility':2.5})
            
            p_h, p_a, vol, hm, am = predict_match_outcome(h, h_i, a_i, parse_market_value(market_value_map.get(h)), parse_market_value(market_value_map.get(a)), 0.5, -1, league_stats.get(lg_code), lg_code)
            adv = calculate_advanced_probs(p_h, p_a, 0.5, vol, -1)
            pick, score = calculate_alpha_pick(adv['h_win'], adv['a_win'], adv['prob_o25'], adv['btts']/100, -1, vol, adv['kelly_h'], adv['kelly_a'], calculate_dominance_index(h_i, a_i))
            
            print(f"         ✅ {h} vs {a} | {pick}")
            
            cleaned.append({
                '時間': t_str, '聯賽': lg_code, '主隊': h, '客隊': a,
                '主排名': h_i['rank'], '客排名': a_i['rank'],
                '主預測': p_h, '客預測': p_a, '總球數': round(p_h+p_a,1),
                '狀態': status, '主分': item['goals']['home'], '客分': item['goals']['away'],
                '主勝率': round(adv['h_win']*100), '和局率': round(adv['draw']*100), '客勝率': round(adv['a_win']*100),
                '大球率2.5': adv['prob_o25'], 'BTTS': adv['btts'],
                '凱利主(%)': adv['kelly_h'], '凱利客(%)': adv['kelly_a'],
                '亞盤建議': calculate_handicap_with_prob(adv['h_win'], adv['a_win'], adv['ah_minus_05'], adv['ah_minus_1'], adv['ah_minus_2']),
                '智能標籤': analyze_team_tags(h_i, a_i, vol, -1, adv['kelly_h'], adv['kelly_a'], calculate_dominance_index(h_i, a_i), adv['prob_o25']),
                '風險評級': calculate_risk_level(adv['ou_conf'], vol, adv['prob_o25'], adv['kelly_h']+adv['kelly_a'], adv['goal_range_high']-adv['goal_range_low']),
                '首選推介': pick
            })
            
    if cleaned:
        df = pd.DataFrame(cleaned)
        cols = ['時間','聯賽','主隊','客隊','主排名','客排名','主預測','客預測','總球數','狀態','主分','客分',
                '主勝率','和局率','客勝率','大球率2.5','BTTS','凱利主(%)','凱利客(%)','亞盤建議','智能標籤','風險評級','首選推介']
        df = df.reindex(columns=cols, fill_value='')
        if spreadsheet:
            try: spreadsheet.sheet1.clear(); spreadsheet.sheet1.update(range_name='A1', values=[df.columns.values.tolist()] + df.astype(str).values.tolist()); print("✅ 數據上傳成功！")
            except: print("❌ 上傳失敗")
    else: print("⚠️ 無比賽數據")

if __name__ == "__main__":
    main()
