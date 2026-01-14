import requests
import pandas as pd
import time
import math
import gspread
from datetime import datetime, timedelta
import pytz
from oauth2client.service_account import ServiceAccountCredentials
import random

# ================= 設定區 =================
API_KEY = '531bb40a089446bdae76a019f2af3beb' 
BASE_URL = 'https://api.football-data.org/v4'
GOOGLE_SHEET_NAME = "數據上傳" 
MANUAL_TAB_NAME = "球隊身價表" 

# [V15.0] 市場與數學係數
MARKET_GOAL_INFLATION = 1.28 
DIXON_COLES_RHO = -0.13 # Dixon-Coles 修正係數 (修正 0-0, 1-1 等低比分偏差)

REQUEST_COUNT = 0

# 聯賽列表
COMPETITIONS = ['PL','PD','CL','SA','BL1','FL1','DED','PPL','ELC','BSA','CLI','WC','EC']

# 聯賽風格係數
LEAGUE_GOAL_FACTOR = {
    'BL1': 1.45, 'DED': 1.55, 'PL': 1.25, 'PD': 1.05,
    'SA': 1.15, 'FL1': 1.10, 'PPL': 1.20, 'BSA': 1.05, 'ELC': 1.15
}

# 豪門名單
TITAN_TEAMS = [
    'Man City', 'Liverpool', 'Arsenal', 'Real Madrid', 'Barça', 'Barcelona', 
    'Atlético', 'Bayern', 'Leverkusen', 'Dortmund', 'PSG', 'Inter', 'Juventus', 
    'Milan', 'Napoli', 'Sporting CP', 'Benfica', 'Porto', 'PSV', 'Feyenoord', 'Ajax'
]

# ================= 智能 API 請求函式 =================
def check_rate_limit():
    global REQUEST_COUNT
    REQUEST_COUNT += 1
    if REQUEST_COUNT % 8 == 0:
        print(f"⏳ [智能限流] 已發送 {REQUEST_COUNT} 次請求，強制休息 62 秒...")
        time.sleep(62)

def call_api_with_retry(url, params=None, headers=None, retries=3):
    check_rate_limit() 
    for i in range(retries):
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                wait_time = 70 
                print(f"🛑 429 限流。暫停 {wait_time} 秒...")
                time.sleep(wait_time)
                continue 
            elif response.status_code >= 400:
                 print(f"⚠️ API 錯誤: {response.status_code} | {url}")
                 return None
        except Exception as e:
            print(f"❌ 連線異常: {e}")
            time.sleep(5)
            continue
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
        return None

def load_manual_market_values(spreadsheet):
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

# ================= [V15.0] 凱利公式與 Alpha 獵殺 =================
def calculate_kelly_stake(prob, odds):
    """
    計算凱利公式建議注碼
    prob: 預測勝率 (0.0 - 1.0)
    odds: 賠率 (小數點格式)
    公式: f = (bp - q) / b
    """
    if odds <= 1: return 0
    b = odds - 1
    q = 1 - prob
    f = (b * prob - q) / b
    return max(0, f * 100) # 返回百分比 (建議本金比例)

def analyze_team_tags(h_info, a_info, match_vol, h2h_avg_goals, kelly_h, kelly_a):
    tags = []
    # 強制轉字串防錯
    h_form = str(h_info.get('form', 'N/A'))
    a_form = str(a_info.get('form', 'N/A'))

    if h_info['home_att'] > 2.2: tags.append("🏠主場龍")
    if a_info['away_def'] > 2.0: tags.append("🚌客場蟲")
    if a_info['away_att'] > 2.0: tags.append("⚔️客場殺手")
    if h_info['home_def'] < 0.8: tags.append("🛡️主場鐵壁")
    if match_vol > 3.5: tags.append("🎆入球機器")
    elif match_vol < 2.0: tags.append("💤悶戰專家")
    if 'WWWW' in h_form: tags.append("🔥主連勝")
    if 'LLLL' in h_form: tags.append("📉主頹勢")
    if h2h_avg_goals > 3.5: tags.append("💣宿敵對攻")
    
    # [V15] 價值標籤
    if kelly_h > 5 or kelly_a > 5: tags.append("💎超值博")
    
    return " ".join(tags) if tags else "⚖️ 數據平衡"

def calculate_alpha_pick(h_win, a_win, prob_o25, prob_btts, h2h_avg, match_vol, kelly_h, kelly_a):
    scores = {}
    
    # 大小球
    scores['2.5大'] = prob_o25 * 100
    if h2h_avg > 3.0: scores['2.5大'] += 15
    if match_vol > 3.2: scores['2.5大'] += 10
    
    scores['2.5細'] = (1 - prob_o25) * 100
    if match_vol < 2.2: scores['2.5細'] += 15
    
    # 主客和 (加入凱利權重 - 這才是最有用的指標)
    # 如果凱利值高，代表計算出的勝率遠高於市場預期，值得加分
    scores['主勝'] = h_win * 100 
    if kelly_h > 0: scores['主勝'] += (kelly_h * 2) # 有價值大幅加分

    scores['客勝'] = a_win * 100 
    if kelly_a > 0: scores['客勝'] += (kelly_a * 2)
    
    # 亞盤/讓球
    scores['主(+0/0.5)'] = (h_win + (1-h_win-a_win)) * 100 
    scores['客(+0/0.5)'] = (a_win + (1-h_win-a_win)) * 100
    
    # BTTS
    scores['BTTS-是'] = prob_btts * 100
    
    # 上半場
    scores['上半大0.5/1'] = 0
    if match_vol > 3.5: scores['上半大0.5/1'] = 85 
    
    # 強制決策
    valid_scores = {k: v for k, v in scores.items()}
    if not valid_scores: return "數據混亂 (避)", 0
    
    best_pick = max(valid_scores, key=valid_scores.get)
    best_score = valid_scores[best_pick]
    
    rating = ""
    if best_score > 85: rating = "(🌟鐵膽)"
    elif best_score > 75: rating = "(🔥重心)"
    elif best_score > 65: rating = "(✅值博)"
    else: rating = "(🤔博冷)" 
    
    return f"{best_pick} {rating}", best_score

def calculate_risk_level(ou_conf, match_vol, prob_o25, kelly_sum):
    score = 50 - (ou_conf - 50)
    if prob_o25 > 0.7 or prob_o25 < 0.3: score -= 20
    
    # 凱利值過高或過低都影響風險判斷
    if kelly_sum > 20: score -= 10 # 高價值通常伴隨風險，但也值得博
    
    if score < 25: return "🟢 極穩"
    elif score < 50: return "🔵 穩健"
    else: return "🔴 高險"

# ================= [V15.0 數學核心 - Dixon-Coles] =================
def calculate_advanced_probs(home_exp, away_exp, h2h_o25_rate, match_vol, h2h_avg_goals):
    def poisson(k, lam): return (lam**k * math.exp(-lam)) / math.factorial(k)
    
    # Dixon-Coles 調整函式 (核心升級: 修正低比分偏差)
    def adjustment(x, y, lam, mu, rho):
        if x == 0 and y == 0: return 1 - (lam * mu * rho)
        if x == 0 and y == 1: return 1 + (lam * rho)
        if x == 1 and y == 0: return 1 + (mu * rho)
        if x == 1 and y == 1: return 1 - rho
        return 1.0

    h_win=0; draw=0; a_win=0
    prob_o15 = 0; prob_o25 = 0; prob_o35 = 0
    
    # 增加計算範圍到 10 球，提高精確度
    for h in range(10): 
        for a in range(10):
            base_prob = poisson(h, home_exp) * poisson(a, away_exp)
            adj = adjustment(h, a, home_exp, away_exp, DIXON_COLES_RHO)
            final_prob = base_prob * adj
            
            # 確保概率非負
            if final_prob < 0: final_prob = 0
            
            if h > a: h_win += final_prob
            elif h == a: draw += final_prob
            else: a_win += final_prob
            
            total = h + a
            if total > 1.5: prob_o15 += final_prob
            if total > 2.5: prob_o25 += final_prob
            if total > 3.5: prob_o35 += final_prob
    
    # 歸一化 (Normalization) - 確保總和為 1 (修正 Dixon-Coles 帶來的微小偏差)
    total_prob = h_win + draw + a_win
    if total_prob > 0:
        h_win /= total_prob; draw /= total_prob; a_win /= total_prob
        prob_o15 /= total_prob; prob_o25 /= total_prob; prob_o35 /= total_prob

    # 估算上半場 > 0.5 (簡易版)
    ht_lambda_h = home_exp * 0.42
    ht_lambda_a = away_exp * 0.42
    prob_ht_00 = poisson(0, ht_lambda_h) * poisson(0, ht_lambda_a)
    prob_ht_o05 = 1 - prob_ht_00
            
    p_h_score = 1 - poisson(0, home_exp)
    p_a_score = 1 - poisson(0, away_exp)
    btts = p_h_score * p_a_score
    
    # 賠率計算 (純機率倒數)
    odds_h = 1/h_win if h_win > 0.01 else 99.0
    odds_d = 1/draw if draw > 0.01 else 99.0
    odds_a = 1/a_win if a_win > 0.01 else 99.0

    limit = 50.0
    # 合理賠率 (Fair Odds) - 這是 V15 最重要的指標 (不含水位的純機率賠率)
    fair_1x2_h = min((1 / max(h_win, 0.01)), limit)
    fair_1x2_d = min((1 / max(draw, 0.01)), limit)
    fair_1x2_a = min((1 / max(a_win, 0.01)), limit)

    fair_o25 = min((1 / max(prob_o25, 0.01)), limit)
    fair_u25 = min((1 / max(1-prob_o25, 0.01)), limit)

    # [實用指標] 最低值博賠率 (Min Value Odds)
    # 這是給用戶看的：如果莊家賠率 > 這個數值，就是 +EV
    # 我們設定一個 5% 的安全邊際 (Margin of Safety)
    safety_margin = 1.05
    min_odds_h = round(fair_1x2_h * safety_margin, 2)
    min_odds_a = round(fair_1x2_a * safety_margin, 2)

    # 模擬凱利指數 (假設市場賠率約為 Fair Odds + 8% 水位，模擬若市場賠率不錯時的建議)
    # 這裡我們計算一個「潛在市場賠率」來做示範
    market_sim_h = fair_1x2_h * 0.95 
    kelly_h = calculate_kelly_stake(h_win, market_sim_h * 1.15) # 模擬如果市場賠率錯價 15%
    kelly_a = calculate_kelly_stake(a_win, fair_1x2_a * 1.05) # 模擬

    math_conf = abs(prob_o25 - 0.5) * 2 * 40
    h2h_conf = 0
    if h2h_avg_goals != -1:
        if h2h_avg_goals > 3.0 and prob_o25 > 0.5: h2h_conf = 35
        elif h2h_avg_goals < 1.5 and prob_o25 < 0.5: h2h_conf = 35
        elif (h2h_avg_goals < 1.8 and prob_o25 > 0.6): h2h_conf = -20
        elif (h2h_avg_goals > 3.0 and prob_o25 < 0.4): h2h_conf = -20
    else: h2h_conf = 5 
        
    vol_conf = 0
    if prob_o25 > 0.5 and match_vol > 3.2: vol_conf = 25
    elif prob_o25 < 0.5 and match_vol < 2.2: vol_conf = 25
    
    total_conf = max(min(math_conf + h2h_conf + vol_conf, 99), 25) 
    
    live_strat = "中性觀望"
    corner_trend = "中"
    if match_vol > 3.1: 
        live_strat = "🔥 追大/絕殺"
        corner_trend = "高"
    elif match_vol < 2.3: 
        live_strat = "🛡️ 半場細/角球"
        corner_trend = "低"
    elif home_exp > away_exp * 2: 
        live_strat = "🏰 主隊控場"
        corner_trend = "主多"
    
    if prob_ht_o05 > 0.72: live_strat += " | 上半有機"
    
    return {
        'btts': round(btts*100, 1), 
        'cs_h': round(poisson(0, away_exp)*100, 1), 
        'cs_a': round(poisson(0, home_exp)*100, 1), 
        'h_win': h_win, 'a_win': a_win,
        'odds_h': round(odds_h, 2), 
        'odds_d': round(odds_d, 2), 
        'odds_a': round(odds_a, 2),
        'prob_o15': round(prob_o15*100, 1),
        'prob_o25': round(prob_o25*100, 1),
        'prob_o35': round(prob_o35*100, 1),
        'prob_ht_o05': round(prob_ht_o05*100, 1), 
        'ou_conf': round(total_conf, 1),
        'h2h_avg_goals': h2h_avg_goals,
        'fair_1x2_h': round(fair_1x2_h, 2),
        'fair_1x2_d': round(fair_1x2_d, 2),
        'fair_1x2_a': round(fair_1x2_a, 2),
        'min_odds_h': min_odds_h, # 最低值博賠率 (關鍵新增)
        'min_odds_a': min_odds_a,
        'fair_o25': round(fair_o25, 2),
        'fair_u25': round(fair_u25, 2), 
        'live_strat': live_strat,
        'corner_trend': corner_trend,
        'kelly_h': round(kelly_h, 1), # 這裡僅作模擬計算
        'kelly_a': round(kelly_a, 1)
    }

def calculate_correct_score_probs(home_exp, away_exp):
    def poisson(k, lam): return (lam**k * math.exp(-lam)) / math.factorial(k)
    scores = []
    for h in range(7):
        for a in range(7):
            prob = poisson(h, home_exp) * poisson(a, away_exp)
            # 簡單 Dixon-Coles 修正顯示
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

# ================= 數據獲取 =================
def get_all_standings_with_stats():
    print("📊 計算聯賽基數...")
    standings_map = {}
    league_stats = {} 
    headers = {'X-Auth-Token': API_KEY}
    
    for i, comp in enumerate(COMPETITIONS):
        url = f"{BASE_URL}/competitions/{comp}/standings"
        data = call_api_with_retry(url, headers=headers)
        if data:
            total_h=0; total_a=0; total_m=0
            tables = data.get('standings', [])
            for table in tables:
                t_type = table['type']
                for entry in table['table']:
                    tid = entry['team']['id']
                    if tid not in standings_map:
                        standings_map[tid] = {'rank':0,'form':'N/A','home_att':1.3,'home_def':1.3,'away_att':1.0,'away_def':1.0,'volatility':2.5,'season_ppg':1.3}
                    
                    played = entry['playedGames']
                    points = entry['points']
                    gf = entry['goalsFor']; ga = entry['goalsAgainst']
                    
                    avg_gf = gf/played if played>0 else 1.35
                    avg_ga = ga/played if played>0 else 1.35

                    if t_type == 'TOTAL':
                        standings_map[tid]['rank'] = entry['position']
                        raw_form = entry.get('form')
                        standings_map[tid]['form'] = str(raw_form) if raw_form else 'N/A'
                        standings_map[tid]['season_ppg'] = points/played if played>0 else 1.3
                        if played > 0: 
                            # 簡單的波動率估算
                            standings_map[tid]['volatility'] = (gf+ga)/played
                    elif t_type == 'HOME':
                        standings_map[tid]['home_att'] = avg_gf
                        standings_map[tid]['home_def'] = avg_ga
                        total_h += gf; 
                        if played>0: total_m += played
                    elif t_type == 'AWAY':
                        standings_map[tid]['away_att'] = avg_gf
                        standings_map[tid]['away_def'] = avg_ga
                        total_a += gf
            
            if total_m > 10:
                avg_h = max(total_h/total_m, 1.55) * 1.05 
                avg_a = max(total_a/total_m, 1.25) * 1.05
            else:
                avg_h = 1.6; avg_a = 1.3
            
            league_stats[data['competition']['code']] = {'avg_home': avg_h, 'avg_away': avg_a}
    return standings_map, league_stats

# ================= 預測模型 =================
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
    is_titan = False
    for titan in TITAN_TEAMS:
        if titan in h_name: is_titan = True; break
            
    if h_v > 0 and a_v > 0:
        ratio = h_v / a_v
        if ratio > 8.0: raw_h *= 1.45; raw_a *= 0.7
        elif ratio > 4.0: raw_h *= 1.25; raw_a *= 0.85
        val_factor = max(min(math.log(ratio) * 0.2, 0.5), -0.5)
        raw_h *= (1 + val_factor); raw_a *= (1 - val_factor)

    if is_titan:
        if raw_h < 1.7: raw_h = max(raw_h * 1.4, 1.95)
        else: raw_h *= 1.15

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

# ================= H2H 函式 =================
def get_h2h_and_ou_stats(match_id, h_id, a_id):
    headers = {'X-Auth-Token': API_KEY}
    url = f"{BASE_URL}/matches/{match_id}/head2head"
    data = call_api_with_retry(url, headers=headers)
    try:
        if data:
            matches = data.get('matches', []) 
            if not matches: return "無對賽記錄", "N/A", -1, -1
            
            matches.sort(key=lambda x: x['utcDate'], reverse=True)
            recent = matches[:10]
            total=0; h_w=0; a_w=0; d=0; o15=0; o25=0; o35=0; total_goals=0
            
            for m in recent:
                if m['status'] != 'FINISHED': continue
                total+=1
                w = m['score']['winner']
                if w == 'DRAW': d+=1
                elif w == 'HOME_TEAM':
                    if m['homeTeam']['id'] == h_id: h_w+=1
                    else: a_w+=1
                elif w == 'AWAY_TEAM':
                    if m['awayTeam']['id'] == h_id: h_w+=1
                    else: a_w+=1
                try:
                    g = m['score']['fullTime']['home'] + m['score']['fullTime']['away']
                    total_goals += g
                    if g>1.5: o15+=1; 
                    if g>2.5: o25+=1; 
                    if g>3.5: o35+=1
                except: pass
            
            if total==0: return "無有效對賽", "N/A", -1, -1
            
            p15=round(o15/total*100); p25=round(o25/total*100); p35=round(o35/total*100)
            avg_g = round(total_goals/total, 1)
            
            h2h_str = f"近{total}場: 主{h_w}勝 | 和{d} | 客{a_w}勝"
            ou_str = f"對賽大球率: 1.5球({p15}%) | 2.5球({p25}%) | 3.5球({p35}%)"
            
            return h2h_str, ou_str, (o25/total), avg_g
        return "N/A", "N/A", -1, -1
    except: return "N/A", "N/A", -1, -1

# ================= 主流程 =================
def get_real_data(market_value_map):
    standings, league_stats = get_all_standings_with_stats()
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 V15.0 Alpha Pro 啟動...")
    headers = {'X-Auth-Token': API_KEY}
    utc_now = datetime.now(pytz.utc)
    start_date = (utc_now - timedelta(days=2)).strftime('%Y-%m-%d') 
    end_date = (utc_now + timedelta(days=5)).strftime('%Y-%m-%d') 
    params = { 'dateFrom': start_date, 'dateTo': end_date, 'competitions': ",".join(COMPETITIONS) }

    try:
        response_json = call_api_with_retry(f"{BASE_URL}/matches", params=params, headers=headers)
        if not response_json: return []
        matches = response_json.get('matches', [])
        if not matches: return []

        cleaned = []
        hk_tz = pytz.timezone('Asia/Hong_Kong')

        for index, match in enumerate(matches):
            utc_dt = datetime.strptime(match['utcDate'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
            time_str = utc_dt.astimezone(hk_tz).strftime('%Y-%m-%d %H:%M') 
            
            status = '進行中' if match['status'] in ['IN_PLAY','PAUSED'] else '完場' if match['status']=='FINISHED' else '延期/取消' if match['status'] in ['POSTPONED','CANCELLED'] else '未開賽'
            
            h_id = match['homeTeam']['id']; a_id = match['awayTeam']['id']
            h_name = match['homeTeam']['shortName'] or match['homeTeam']['name']
            a_name = match['awayTeam']['shortName'] or match['awayTeam']['name']
            lg_code = match['competition']['code']
            lg_name = match['competition']['name']
            
            h_info = standings.get(h_id, {'rank':10,'form':'N/A','home_att':1.3,'home_def':1.3,'volatility':2.5,'season_ppg':1.3})
            a_info = standings.get(a_id, {'rank':10,'form':'N/A','away_att':1.1,'away_def':1.1,'volatility':2.5,'season_ppg':1.3})
            h_val = market_value_map.get(h_name, "N/A"); a_val = market_value_map.get(a_name, "N/A")
            
            h2h_str, ou_str, h2h_o25_rate, h2h_avg = get_h2h_and_ou_stats(match['id'], h_id, a_id)
            lg_avg = league_stats.get(lg_code, {'avg_home': 1.6, 'avg_away': 1.3})
            
            pred_h, pred_a, vol, h_mom, a_mom = predict_match_outcome(
                h_name, h_info, a_info, h_val, a_val, h2h_o25_rate, h2h_avg, lg_avg, lg_code
            )
            
            correct_score_str = calculate_correct_score_probs(pred_h, pred_a)
            adv_stats = calculate_advanced_probs(pred_h, pred_a, h2h_o25_rate, vol, h2h_avg)
            
            kelly_sum = adv_stats['kelly_h'] + adv_stats['kelly_a']
            smart_tags = analyze_team_tags(h_info, a_info, vol, h2h_avg, adv_stats['kelly_h'], adv_stats['kelly_a'])
            risk_level = calculate_risk_level(adv_stats['ou_conf'], vol, adv_stats['prob_o25'], kelly_sum)
            
            top_pick, pick_score = calculate_alpha_pick(
                adv_stats['h_win'], adv_stats['a_win'], 
                adv_stats['prob_o25'], adv_stats['btts']/100, 
                h2h_avg, vol, adv_stats['kelly_h'], adv_stats['kelly_a']
            )

            score_h = match['score']['fullTime']['home']
            score_a = match['score']['fullTime']['away']
            if score_h is None: score_h = ''
            if score_a is None: score_a = ''

            print(f"   ✅ 分析 [{index+1}/{len(matches)}]: {h_name} vs {a_name} | Alpha:{top_pick}")

            cleaned.append({
                '時間': time_str, '聯賽': lg_name,
                '主隊': h_name, '客隊': a_name,
                '主排名': h_info['rank'], '客排名': a_info['rank'],
                '主近況': h_info['form'], '客近況': a_info['form'],
                '主預測': pred_h, '客預測': pred_a,
                '總球數': round(pred_h + pred_a, 1),
                '主攻(H)': round(pred_h * 1.2, 1), '客攻(A)': round(pred_a * 1.2, 1),
                '狀態': status,
                '主分': score_h, '客分': score_a,
                'H2H': h2h_str, '大小球統計': ou_str,
                'H2H平均球': h2h_avg,
                '主隊身價': h_val, '客隊身價': a_val,
                '賽事風格': vol, '主動量': h_mom, '客動量': a_mom,
                '波膽預測': correct_score_str,
                'BTTS': adv_stats['btts'],
                '主零封': adv_stats['cs_h'], '客零封': adv_stats['cs_a'],
                
                '大球率1.5': adv_stats['prob_o15'], 
                '大球率2.5': adv_stats['prob_o25'],
                '大球率3.5': adv_stats['prob_o35'], 
                '上半大0.5': adv_stats['prob_ht_o05'],
                'OU信心': adv_stats['ou_conf'],
                
                '合理主賠': adv_stats['fair_1x2_h'],
                '合理和賠': adv_stats['fair_1x2_d'],
                '合理客賠': adv_stats['fair_1x2_a'],
                '最低賠率主': adv_stats['min_odds_h'],
                '最低賠率客': adv_stats['min_odds_a'],
                '合理大賠2.5': adv_stats['fair_o25'], 
                '合理細賠2
