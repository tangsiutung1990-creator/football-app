import requests
import pandas as pd
import gspread
from datetime import datetime, timedelta
import pytz
from oauth2client.service_account import ServiceAccountCredentials
import math

# ================= 設定區 (Pro Plan) =================
# 請確認這是你的 Pro Key
API_KEY = '6bf59594223b07234f75a8e2e2de5178' 
BASE_URL = 'https://v3.football.api-sports.io'
GOOGLE_SHEET_NAME = "數據上傳" 
MANUAL_TAB_NAME = "球隊身價表" 

# 聯賽 ID 對照表 (只保留主要聯賽，Pro Plan 可加更多)
# 39:英超, 140:西甲, 135:意甲, 78:德甲, 61:法甲, 2:歐聯, 1:世界盃
LEAGUE_ID_MAP = {
    39: '英超',
    140: '西甲',
    135: '意甲',
    78: '德甲',
    61: '法甲'
}

# 參數設定 (用於 AI 勝率計算)
MARKET_GOAL_INFLATION = 1.25 
DIXON_COLES_RHO = -0.13 

# 聯賽入球系數 (用於調整攻擊力)
LEAGUE_GOAL_FACTOR = {
    '德甲': 1.45, '英超': 1.25, '西甲': 1.05,
    '意甲': 1.15, '法甲': 1.10
}

# ================= API 連接工具 =================
def call_api(endpoint, params=None):
    """通用 API 請求函式"""
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
            print(f"⚠️ API Error {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"❌ 連線異常: {e}")
        return None

# ================= Google Sheet 工具 =================
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

# ================= 核心分析模型 (保留勝率計算) =================
def calculate_kelly_stake(prob, odds):
    """凱利公式: 計算投資價值"""
    if odds <= 1: return 0
    b = odds - 1
    q = 1 - prob
    f = (b * prob - q) / b
    return max(0, f * 100) 

def calculate_weighted_form_score(form_str):
    """計算近況分數"""
    if not form_str or form_str == 'N/A': return 1.5 
    score = 0; total_weight = 0
    relevant = str(form_str).replace(',', '').strip()[-5:]
    weights = [1.0, 1.2, 1.4, 1.8, 2.2] 
    start_idx = 5 - len(relevant)
    if start_idx < 0: start_idx = 0
    curr_weights = weights[start_idx:]
    
    for i, char in enumerate(relevant):
        if i >= len(curr_weights): break
        w = curr_weights[i]
        s = 3 if char.upper()=='W' else 1 if char.upper()=='D' else 0
        score += s * w
        total_weight += w
    return score / total_weight if total_weight > 0 else 1.5

def predict_match_probs(h_name, h_info, a_info, h_val, a_val, lg_stats, lg_code):
    """
    AI 核心: 使用 Dixon-Coles 模型計算勝平負概率
    """
    # 1. 獲取聯賽平均值
    lg_h = lg_stats.get('avg_home', 1.5)
    lg_a = lg_stats.get('avg_away', 1.2)
    
    # 2. 計算攻防能力值
    h_att = h_info['home_att'] / lg_h
    h_def = h_info['home_def'] / lg_a
    a_att = a_info['away_att'] / lg_a
    a_def = a_info['away_def'] / lg_h
    
    # 3. 預期入球 (Lambda)
    factor = LEAGUE_GOAL_FACTOR.get(lg_code, 1.1)
    home_exp = h_att * a_def * lg_h * factor
    away_exp = a_att * h_def * lg_a * factor
    
    # 4. 身價修正
    if h_val > 0 and a_val > 0:
        ratio = h_val / a_val
        val_factor = max(min(math.log(ratio) * 0.15, 0.4), -0.4)
        home_exp *= (1 + val_factor)
        away_exp *= (1 - val_factor)
        
    # 5. 近況修正
    h_mom = calculate_weighted_form_score(h_info['form'])
    a_mom = calculate_weighted_form_score(a_info['form'])
    home_exp *= (1 + (h_mom - 1.5) * 0.1)
    away_exp *= (1 + (a_mom - 1.5) * 0.1)
    
    # 6. Poisson 分佈計算勝率
    def poisson(k, lam): return (lam**k * math.exp(-lam)) / math.factorial(k)
    
    h_win = 0; draw = 0; a_win = 0; prob_o25 = 0; prob_btts = 0
    
    for h in range(7):
        for a in range(7):
            prob = poisson(h, home_exp) * poisson(a, away_exp)
            
            # Dixon-Coles 調整 (針對 0-0, 1-0, 0-1, 1-1 的低比分修正)
            if h==0 and a==0: prob *= (1 - home_exp*away_exp*DIXON_COLES_RHO)
            elif h==0 and a==1: prob *= (1 + home_exp*DIXON_COLES_RHO)
            elif h==1 and a==0: prob *= (1 + away_exp*DIXON_COLES_RHO)
            elif h==1 and a==1: prob *= (1 - DIXON_COLES_RHO)
            
            if h > a: h_win += prob
            elif h == a: draw += prob
            else: a_win += prob
            
            if (h + a) > 2.5: prob_o25 += prob
            if h > 0 and a > 0: prob_btts += prob

    # 正規化
    total_prob = h_win + draw + a_win
    return {
        'h_win': h_win/total_prob, 
        'draw': draw/total_prob, 
        'a_win': a_win/total_prob,
        'prob_o25': prob_o25/total_prob,
        'btts': prob_btts/total_prob,
        'exp_h': home_exp,
        'exp_a': away_exp
    }

# ================= 數據獲取流程 =================

def get_real_odds(fixture_id):
    """
    獲取真實賠率 (Bet365)
    """
    data = call_api('odds', {'fixture': fixture_id, 'bookmaker': 1}) # 1 = Bet365
    if data and data['response']:
        bets = data['response'][0]['bookmakers'][0]['bets']
        win_odds = next((b for b in bets if b['name'] == 'Match Winner'), None)
        o25_odds = next((b for b in bets if b['name'] == 'Goals Over/Under'), None)
        
        odds_h = 0; odds_d = 0; odds_a = 0; odds_o25 = 0
        
        if win_odds:
            for v in win_odds['values']:
                if v['value'] == 'Home': odds_h = float(v['odd'])
                elif v['value'] == 'Draw': odds_d = float(v['odd'])
                elif v['value'] == 'Away': odds_a = float(v['odd'])
        
        if o25_odds:
             for v in o25_odds['values']:
                 if v['value'] == 'Over 2.5': odds_o25 = float(v['odd'])
                 
        return odds_h, odds_d, odds_a, odds_o25
    return 0, 0, 0, 0

def get_standings(season):
    print(f"📊 [API-Football] 下載 {season} 賽季積分榜...")
    standings_map = {}
    league_stats = {} 
    
    for lg_id, lg_name in LEAGUE_ID_MAP.items():
        data = call_api('standings', {'league': lg_id, 'season': season})
        
        if not data or not data.get('response'):
            print(f"   ⚠️ 無法獲取 {lg_name} 積分榜")
            continue
            
        l_h_g = 0; l_m = 0
        
        # 處理每一個分組 (有些聯賽有多個 Group)
        standings_list = data['response'][0]['league']['standings']
        # 扁平化 list
        all_rows = [item for sublist in standings_list for item in sublist]

        for row in all_rows:
            t_name = row['team']['name']
            p = row['all']['played']
            h_p = row['home']['played']; a_p = row['away']['played']
            
            # 避免除以零
            h_att = row['home']['goals']['for'] / h_p if h_p > 0 else 1.3
            h_def = row['home']['goals']['against'] / h_p if h_p > 0 else 1.3
            a_att = row['away']['goals']['for'] / a_p if a_p > 0 else 1.0
            a_def = row['away']['goals']['against'] / a_p if a_p > 0 else 1.0
            
            standings_map[t_name] = {
                'rank': row['rank'],
                'form': row['form'], # 真實近況 (e.g., "WWLDW")
                'home_att': h_att, 'home_def': h_def,
                'away_att': a_att, 'away_def': a_def
            }
            
            l_h_g += row['home']['goals']['for']
            l_m += h_p
            
        # 計算聯賽平均主場入球 (用於模型基準)
        avg_h = l_h_g / l_m if l_m > 0 else 1.5
        league_stats[lg_name] = {'avg_home': avg_h, 'avg_away': avg_h * 0.85} # 客場通常稍弱
        print(f"   ✅ {lg_name} 更新完成")
        
    return standings_map, league_stats

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 V17.0 Pro Edition (Real Data Only) 啟動...")
    
    # 1. 智能賽季判斷 (處理 2026年問題)
    now = datetime.now()
    # 如果是 2026年，我們應該查看 2025 賽季
    season = now.year - 1 if now.month <= 7 else now.year
    # 強制修正: 如果你在 2026年1月，API 的 current season 是 2025
    season = 2025 
    
    # 2. 獲取真實積分榜
    standings_map, league_stats = get_standings(season)
    
    # 3. 獲取真實賽程
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    utc_now = datetime.now(pytz.utc)
    from_date = utc_now.strftime('%Y-%m-%d')
    to_date = (utc_now + timedelta(days=3)).strftime('%Y-%m-%d')
    
    print(f"🚀 掃描賽程 ({from_date} to {to_date})...")
    
    cleaned_data = []
    
    for lg_id, lg_name in LEAGUE_ID_MAP.items():
        # 獲取賽程
        fixtures = call_api('fixtures', {'league': lg_id, 'season': season, 'from': from_date, 'to': to_date})
        
        if not fixtures or not fixtures.get('response'): continue
        
        print(f"   🔍 {lg_name}: 發現 {len(fixtures['response'])} 場比賽")
        
        # 讀取身價表
        spreadsheet = get_google_spreadsheet()
        market_value_map = load_manual_market_values(spreadsheet)

        for item in fixtures['response']:
            fixture = item['fixture']
            home_team = item['teams']['home']['name']
            away_team = item['teams']['away']['name']
            
            # 時間
            dt_obj = datetime.fromtimestamp(fixture['timestamp'], pytz.utc)
            time_str = dt_obj.astimezone(hk_tz).strftime('%Y-%m-%d %H:%M')
            status = '進行中' if fixture['status']['short'] in ['1H','2H','HT','LIVE'] else '未開賽'
            if fixture['status']['short'] in ['FT','AET','PEN']: status = '完場'

            # 獲取球隊數據 (如果沒有數據，使用默認值)
            h_info = standings_map.get(home_team, {'rank':99,'form':'?????','home_att':1.3,'home_def':1.3})
            a_info = standings_map.get(away_team, {'rank':99,'form':'?????','away_att':1.1,'away_def':1.1})
            
            # 獲取真實賠率 (這是 V17.0 的核心升級)
            # 注意: 如果比賽未開盤，賠率會是 0
            odds_h, odds_d, odds_a, odds_o25 = get_real_odds(fixture['id'])
            
            # AI 預測 (只保留勝率計算，刪除假 xG)
            probs = predict_match_probs(
                home_team, h_info, a_info,
                parse_market_value(market_value_map.get(home_team)),
                parse_market_value(market_value_map.get(away_team)),
                league_stats.get(lg_name, {'avg_home':1.5, 'avg_away':1.2}),
                lg_name
            )
            
            # 計算 EV (期望值) - 使用真實賠率
            kelly_h = calculate_kelly_stake(probs['h_win'], odds_h)
            kelly_a = calculate_kelly_stake(probs['a_win'], odds_a)
            
            # 首選推介邏輯
            pick = "觀望"
            if probs['prob_o25'] > 0.6: pick = "大球"
            elif probs['prob_o25'] < 0.4: pick = "細球"
            elif probs['h_win'] > 0.5: pick = "主勝"
            elif probs['a_win'] > 0.45: pick = "客勝"
            
            # 標籤生成
            tags = []
            if kelly_h > 5: tags.append(f"💎主EV({int(kelly_h)}%)")
            if kelly_a > 5: tags.append(f"💎客EV({int(kelly_a)}%)")
            if odds_h > 0: tags.append("📊已開盤")
            tag_str = " ".join(tags)

            print(f"      ✅ 分析: {home_team} vs {away_team} | {pick} | 賠率: {odds_h}/{odds_a}")

            cleaned_data.append({
                '時間': time_str, '聯賽': lg_name,
                '主隊': home_team, '客隊': away_team,
                '主排名': h_info['rank'], '客排名': a_info['rank'],
                '主近況': h_info['form'], '客近況': a_info['form'],
                
                # 真實數據
                '主勝賠率': odds_h if odds_h > 0 else '', 
                '客勝賠率': odds_a if odds_a > 0 else '',
                
                # AI 預測數據
                '主勝率': f"{int(probs['h_win']*100)}%",
                '和局率': f"{int(probs['draw']*100)}%",
                '客勝率': f"{int(probs['a_win']*100)}%",
                '大球率': f"{int(probs['prob_o25']*100)}%",
                'BTTS率': f"{int(probs['btts']*100)}%",
                
                '狀態': status,
                '主分': item['goals']['home'] if item['goals']['home'] is not None else '',
                '客分': item['goals']['away'] if item['goals']['away'] is not None else '',
                '智能標籤': tag_str,
                '首選推介': pick
            })

    # 上傳至 Google Sheet
    if cleaned_data:
        df = pd.DataFrame(cleaned_data)
        # 重新排序欄位
        cols = ['時間','聯賽','主隊','客隊','狀態','主分','客分',
                '主排名','客排名','主近況','客近況',
                '主勝賠率','客勝賠率',
                '主勝率','和局率','客勝率','大球率','BTTS率',
                '智能標籤','首選推介']
        # 確保所有欄位都存在
        for c in cols:
            if c not in df.columns: df[c] = ''
        df = df[cols]
        
        if spreadsheet:
            try:
                sheet = spreadsheet.sheet1
                sheet.clear()
                sheet.update(range_name='A1', values=[df.columns.values.tolist()] + df.astype(str).values.tolist())
                print("✅ 數據上傳成功！所有假數據已刪除，僅保留真實賠率與 AI 勝率預測。")
            except Exception as e:
                print(f"❌ Google Sheet 上傳失敗: {e}")
    else:
        print("⚠️ 無比賽數據 (請檢查日期範圍或聯賽賽程)")

if __name__ == "__main__":
    main()
