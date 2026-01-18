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

# ================= 純數學運算核心 (No Guesses) =================
def poisson_prob(k, lam):
    if lam < 0: lam = 0
    return (math.pow(lam, k) * math.exp(-lam)) / math.factorial(k)

def calculate_advanced_math_probs(h_exp, a_exp):
    """
    使用 Poisson 矩陣積分計算所有盤口，不含任何人工權重
    """
    h_exp = float(h_exp)
    a_exp = float(a_exp)
    
    # 矩陣變數
    prob_exact_score = {} # 儲存波膽概率
    
    # 1. 建立波膽矩陣 (0-0 到 9-9)
    for h in range(10):
        for a in range(10):
            p = poisson_prob(h, h_exp) * poisson_prob(a, a_exp)
            prob_exact_score[(h, a)] = p

    # 2. 積分計算 (Integrate)
    # 大小球
    o05 = sum(p for (h, a), p in prob_exact_score.items() if h+a > 0.5)
    o15 = sum(p for (h, a), p in prob_exact_score.items() if h+a > 1.5)
    o25 = sum(p for (h, a), p in prob_exact_score.items() if h+a > 2.5)
    o35 = sum(p for (h, a), p in prob_exact_score.items() if h+a > 3.5)
    
    # 亞盤/讓球 (精確數學)
    # 主贏 (Win)
    h_win = sum(p for (h, a), p in prob_exact_score.items() if h > a)
    # 和局 (Draw)
    draw = sum(p for (h, a), p in prob_exact_score.items() if h == a)
    # 客贏 (Loss)
    a_win = sum(p for (h, a), p in prob_exact_score.items() if a > h)
    
    # 輸贏球差概率
    # 主剛好贏 1 球 (e.g. 1-0, 2-1)
    h_win_1 = sum(p for (h, a), p in prob_exact_score.items() if h - a == 1)
    # 主剛好贏 2 球
    h_win_2 = sum(p for (h, a), p in prob_exact_score.items() if h - a == 2)
    # 客剛好贏 1 球 (主輸 1 球)
    a_win_1 = sum(p for (h, a), p in prob_exact_score.items() if a - h == 1)
    # 客剛好贏 2 球 (主輸 2 球)
    a_win_2 = sum(p for (h, a), p in prob_exact_score.items() if a - h == 2)

    # 3. 亞盤機率推導 (Probability of Non-Loss)
    # 平手盤 (0): 視為獨贏 (在平局退款機制下，勝率相對比例不變)
    # 這裡顯示的是「贏盤率」，即 (Win) / (Win + Loss)
    ah_level_h = h_win / (h_win + a_win + 0.00001)
    ah_level_a = a_win / (h_win + a_win + 0.00001)
    
    # +0.5 (不敗): 贏 + 和
    ah_plus05_h = h_win + draw
    ah_plus05_a = a_win + draw
    
    # +1.0 (輸1球走盤): 贏盤率 = (贏+和)。不輸盤率 = (贏+和+輸1)。
    # 這裡我們計算「不輸盤率 (Not Lose Bet)」
    ah_plus1_h = h_win + draw + a_win_1
    ah_plus1_a = a_win + draw + h_win_1
    
    # +2.0 (輸2球走盤): 不輸盤率 = (贏+和+輸1+輸2)
    ah_plus2_h = h_win + draw + a_win_1 + a_win_2
    ah_plus2_a = a_win + draw + h_win_1 + h_win_2
    
    # -2.0 (必須贏3球): 
    ah_minus2_h = sum(p for (h, a), p in prob_exact_score.items() if h - a > 2)
    ah_minus2_a = sum(p for (h, a), p in prob_exact_score.items() if a - h > 2)

    # 4. 半場計算 (HT)
    # 假設半場 lambda 為全場的 45%
    ht_prob_score = {}
    for h in range(6):
        for a in range(6):
            p = poisson_prob(h, h_exp*0.45) * poisson_prob(a, a_exp*0.45)
            ht_prob_score[(h, a)] = p
            
    ht_o05 = sum(p for (h, a), p in ht_prob_score.items() if h+a > 0.5)
    ht_o15 = sum(p for (h, a), p in ht_prob_score.items() if h+a > 1.5)
    ht_o25 = sum(p for (h, a), p in ht_prob_score.items() if h+a > 2.5)

    return {
        'o05': round(o05*100), 'o15': round(o15*100), 'o25': round(o25*100), 'o35': round(o35*100),
        'ht_o05': round(ht_o05*100), 'ht_o15': round(ht_o15*100), 'ht_o25': round(ht_o25*100),
        'ah_level_h': round(ah_level_h*100), 'ah_plus05_h': round(ah_plus05_h*100), 
        'ah_plus1_h': round(ah_plus1_h*100), 'ah_plus2_h': round(ah_plus2_h*100), 'ah_minus2_h': round(ah_minus2_h*100),
        'ah_level_a': round(ah_level_a*100), 'ah_plus05_a': round(ah_plus05_a*100), 
        'ah_plus1_a': round(ah_plus1_a*100), 'ah_plus2_a': round(ah_plus2_a*100), 'ah_minus2_a': round(ah_minus2_a*100)
    }

def calculate_kelly_stake(prob, odds):
    if odds <= 1: return 0
    b = odds - 1; q = 1 - prob; f = (b * prob - q) / b
    return max(0, f * 100)

def clean_percent_str(val_str):
    if not val_str: return 0
    try: return int(float(str(val_str).replace('%', '')))
    except: return 0

def get_best_odds(fixture_id):
    data = call_api('odds', {'fixture': fixture_id})
    if not data or not data.get('response'): return 0, 0, 0
    
    bookmakers = data['response'][0]['bookmakers']
    # 擴大搜尋範圍，只要有賠率就拿
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

# ================= 主流程 =================
def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 V27.0 API-Native (Pure Math Core) 啟動...")
    
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    utc_now = datetime.now(pytz.utc)
    from_date = (utc_now - timedelta(days=7)).strftime('%Y-%m-%d')
    to_date = (utc_now + timedelta(days=3)).strftime('%Y-%m-%d')
    season = 2025 
    
    print(f"📅 掃描範圍: {from_date} 至 {to_date} (Season {season})")
    
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

            # === API 預測 ===
            pred_resp = call_api('predictions', {'fixture': fix_id})
            
            api_h_win=0; api_draw=0; api_a_win=0
            api_goals_h=1.2; api_goals_a=1.0
            advice="暫無"; form_h="50%"; form_a="50%"
            confidence_score = 0
            
            if pred_resp and pred_resp.get('response'):
                pred = pred_resp['response'][0]
                api_h_win = clean_percent_str(pred['predictions']['percent']['home'])
                api_draw = clean_percent_str(pred['predictions']['percent']['draw'])
                api_a_win = clean_percent_str(pred['predictions']['percent']['away'])
                advice = pred['predictions'].get('advice', '觀望')
                confidence_score = max(api_h_win, api_draw, api_a_win)
                
                try:
                    form_h = pred['comparison']['form']['home']
                    form_a = pred['comparison']['form']['away']
                    api_goals_h = float(pred['teams']['home']['last_5']['goals']['for']['average'])
                    api_goals_a = float(pred['teams']['away']['last_5']['goals']['for']['average'])
                    if api_goals_h == 0: api_goals_h = 0.5
                    if api_goals_a == 0: api_goals_a = 0.5
                except: pass

            odds_h = 0; odds_a = 0
            if status != '完場':
                odds_h, odds_d, odds_a = get_best_odds(fix_id)

            # === 純數學運算 (No Weights) ===
            math_probs = calculate_advanced_math_probs(api_goals_h, api_goals_a)
            
            kelly_h = calculate_kelly_stake(api_h_win/100, odds_h)
            kelly_a = calculate_kelly_stake(api_a_win/100, odds_a)

            cleaned_data.append({
                '時間': t_str, '聯賽': lg_name, '主隊': h_name, '客隊': a_name,
                '狀態': status, '主分': score_h_display, '客分': score_a_display,
                
                '主勝率': api_h_win, '和局率': api_draw, '客勝率': api_a_win,
                
                '大0.5': math_probs['o05'], '大1.5': math_probs['o15'],
                '大2.5': math_probs['o25'], '大3.5': math_probs['o35'],
                'HT0.5': math_probs['ht_o05'], 'HT1.5': math_probs['ht_o15'], 'HT2.5': math_probs['ht_o25'],
                
                '主平': math_probs['ah_level_h'], '主+0.5': math_probs['ah_plus05_h'], 
                '主+1': math_probs['ah_plus1_h'], '主+2': math_probs['ah_plus2_h'], '主-2': math_probs['ah_minus2_h'],
                
                '客平': math_probs['ah_level_a'], '客+0.5': math_probs['ah_plus05_a'], 
                '客+1': math_probs['ah_plus1_a'], '客+2': math_probs['ah_plus2_a'], '客-2': math_probs['ah_minus2_a'],

                '主賠': odds_h, '客賠': odds_a,
                '凱利主': round(kelly_h), '凱利客': round(kelly_a),
                '推介': advice, '信心': confidence_score,
                '主狀態': form_h, '客狀態': form_a
            })
            print(f"         ✅ {h_name} vs {a_name} | 信心: {confidence_score}%")

    if cleaned_data:
        df = pd.DataFrame(cleaned_data)
        cols = ['時間','聯賽','主隊','客隊','狀態','主分','客分',
                '主勝率','和局率','客勝率',
                '大0.5','大1.5','大2.5','大3.5',
                'HT0.5','HT1.5','HT2.5',
                '主平','主+0.5','主+1','主+2','主-2',
                '客平','客+0.5','客+1','客+2','客-2',
                '主賠','客賠','凱利主','凱利客','推介','信心','主狀態','客狀態']
        
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
