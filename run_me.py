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
    # 五大聯賽
    39: '英超', 140: '西甲', 135: '意甲', 78: '德甲', 61: '法甲',
    # 次級與歐洲
    40: '英冠', 41: '英甲', 42: '英乙', 141: '西乙', 
    88: '荷甲', 94: '葡超', 144: '比甲', 179: '蘇超', 203: '土超',
    119: '丹超', 113: '瑞典超', 103: '挪超',
    # 亞洲/美洲/其他
    98: '日職', 292: '韓K1', 188: '澳職', 
    253: '美職', 262: '墨超', 71: '巴甲', 128: '阿甲', 265: '智甲',
    # 盃賽
    2: '歐聯', 3: '歐霸'
}

# ================= API 連接函式 =================
def call_api(endpoint, params=None):
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-apisports-key': API_KEY}
    url = f"{BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200: return response.json()
        return None
    except: return None

# ================= Google Sheet 連接 =================
def get_google_spreadsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        client = gspread.authorize(creds)
        return client.open(GOOGLE_SHEET_NAME)
    except: return None

# ================= 純數學運算 (無權重) =================
def poisson_prob(k, lam):
    """標準泊松分佈公式"""
    if lam < 0: lam = 0
    return (math.pow(lam, k) * math.exp(-lam)) / math.factorial(k)

def calculate_exact_goals_probs(home_goals_exp, away_goals_exp):
    """
    利用 API 的預期入球數，推算大小球機率 (純數學轉換，無人工權重)
    """
    # 如果 API 預測入球是負數或無數據，使用保守預設值
    h_exp = float(home_goals_exp) if home_goals_exp is not None else 1.2
    a_exp = float(away_goals_exp) if away_goals_exp is not None else 1.0
    
    # 全場
    prob_o05 = 0; prob_o15 = 0; prob_o25 = 0; prob_o35 = 0
    
    # 半場 (假設分佈約為全場的 45%)
    ht_h_exp = h_exp * 0.45
    ht_a_exp = a_exp * 0.45
    prob_ht_o05 = 0; prob_ht_o15 = 0; prob_ht_o25 = 0
    
    # 循環計算矩陣 (全場)
    for h in range(8):
        for a in range(8):
            p = poisson_prob(h, h_exp) * poisson_prob(a, a_exp)
            total = h + a
            if total > 0.5: prob_o05 += p
            if total > 1.5: prob_o15 += p
            if total > 2.5: prob_o25 += p
            if total > 3.5: prob_o35 += p
            
    # 循環計算矩陣 (半場)
    for h in range(5):
        for a in range(5):
            p = poisson_prob(h, ht_h_exp) * poisson_prob(a, ht_a_exp)
            total = h + a
            if total > 0.5: prob_ht_o05 += p
            if total > 1.5: prob_ht_o15 += p
            if total > 2.5: prob_ht_o25 += p

    return {
        'o05': min(99, round(prob_o05*100)),
        'o15': min(99, round(prob_o15*100)),
        'o25': min(99, round(prob_o25*100)),
        'o35': min(99, round(prob_o35*100)),
        'ht_o05': min(99, round(prob_ht_o05*100)),
        'ht_o15': min(99, round(prob_ht_o15*100)),
        'ht_o25': min(99, round(prob_ht_o25*100))
    }

def clean_percent_str(val_str):
    """將 API 的 '45%' 字串轉換為整數 45"""
    if not val_str: return 0
    try:
        clean = str(val_str).replace('%', '')
        return int(float(clean))
    except: return 0

def calculate_kelly_stake(prob, odds):
    if odds <= 1: return 0
    b = odds - 1; q = 1 - prob; f = (b * prob - q) / b
    return max(0, f * 100) 

# ================= 主流程 =================
def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 V24.1 API-Native (No Streamlit Dependency) 啟動...")
    
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    utc_now = datetime.now(pytz.utc)
    
    # 過去 7 天 + 未來 3 天
    from_date = (utc_now - timedelta(days=7)).strftime('%Y-%m-%d')
    to_date = (utc_now + timedelta(days=3)).strftime('%Y-%m-%d')
    # 強制鎖定 2025 賽季
    season = 2025
    
    print(f"📅 掃描範圍: {from_date} 至 {to_date} (Season {season})")
    
    cleaned_data = []
    
    # 1. 獲取所有賽程
    for lg_id, lg_name in LEAGUE_ID_MAP.items():
        print(f"   🔍 掃描 {lg_name} ({lg_id})...")
        fixtures_data = call_api('fixtures', {'league': lg_id, 'season': season, 'from': from_date, 'to': to_date})
        
        if not fixtures_data or not fixtures_data.get('response'): 
            continue
            
        fixtures = fixtures_data['response']
        print(f"      👉 找到 {len(fixtures)} 場比賽，正在獲取詳細預測...")
        
        for item in fixtures:
            fix_id = item['fixture']['id']
            t_str = datetime.fromtimestamp(item['fixture']['timestamp'], pytz.utc).astimezone(hk_tz).strftime('%Y-%m-%d %H:%M')
            
            # 狀態過濾
            s_short = item['fixture']['status']['short']
            if s_short in ['PST', 'CANC', 'ABD']: status = '延遲/取消'
            elif s_short in ['FT', 'AET', 'PEN']: status = '完場'
            elif s_short in ['1H', '2H', 'HT', 'LIVE']: status = '進行中'
            else: status = '未開賽'

            h_name = item['teams']['home']['name']
            a_name = item['teams']['away']['name']
            score_str = f"{item['goals']['home']}-{item['goals']['away']}" if item['goals']['home'] is not None else "vs"

            # === 核心：獲取 API 官方預測 (取代本地計算) ===
            pred_resp = call_api('predictions', {'fixture': fix_id})
            
            # 預設值
            api_h_win = 0; api_draw = 0; api_a_win = 0
            api_goals_h = 1.2; api_goals_a = 1.0 # 預設值
            advice = "暫無"
            
            if pred_resp and pred_resp.get('response'):
                pred = pred_resp['response'][0]
                
                # 1. 勝率 (來自 API)
                api_h_win = clean_percent_str(pred['predictions']['percent']['home'])
                api_draw = clean_percent_str(pred['predictions']['percent']['draw'])
                api_a_win = clean_percent_str(pred['predictions']['percent']['away'])
                
                # 2. 預期入球 (來自 API)
                try:
                    att_h = float(pred['teams']['home']['last_5']['goals']['for']['average'])
                    att_a = float(pred['teams']['away']['last_5']['goals']['for']['average'])
                    api_goals_h = att_h if att_h > 0 else 1.0
                    api_goals_a = att_a if att_a > 0 else 0.8
                except: pass
                
                advice = pred['predictions'].get('advice', '觀望')

            # === 獲取真實賠率 (Bet365) ===
            odds_h = 0; odds_d = 0; odds_a = 0
            if status != '完場':
                odds_resp = call_api('odds', {'fixture': fix_id, 'bookmaker': 1})
                if odds_resp and odds_resp.get('response'):
                    try:
                        bets = odds_resp['response'][0]['bookmakers'][0]['bets']
                        winner_bet = next((b for b in bets if b['name'] == 'Match Winner'), None)
                        if winner_bet:
                            for o in winner_bet['values']:
                                if o['value'] == 'Home': odds_h = float(o['odd'])
                                if o['value'] == 'Draw': odds_d = float(o['odd'])
                                if o['value'] == 'Away': odds_a = float(o['odd'])
                    except: pass

            # === 數學計算 ===
            ou_probs = calculate_exact_goals_probs(api_goals_h, api_goals_a)
            
            # 亞盤概率
            total_win = api_h_win + api_a_win + 0.01
            ah_level_h = round((api_h_win / total_win) * 100)
            ah_level_a = round((api_a_win / total_win) * 100)
            
            ah_plus05_h = api_h_win + api_draw
            ah_plus05_a = api_a_win + api_draw
            
            kelly_h = calculate_kelly_stake(api_h_win/100, odds_h)
            kelly_a = calculate_kelly_stake(api_a_win/100, odds_a)

            # 準備數據行
            row_data = {
                '時間': t_str, '聯賽': lg_name, '主隊': h_name, '客隊': a_name,
                '狀態': status, '比分': score_str,
                '主分': item['goals']['home'], '客分': item['goals']['away'],
                
                # API 官方預測
                '主勝率': api_h_win, '和局率': api_draw, '客勝率': api_a_win,
                
                # 數學推導數據
                '大0.5': ou_probs['o05'], '大1.5': ou_probs['o15'],
                '大2.5': ou_probs['o25'], '大3.5': ou_probs['o35'],
                'HT0.5': ou_probs['ht_o05'], 'HT1.5': ou_probs['ht_o15'], 'HT2.5': ou_probs['ht_o25'],
                
                # 亞盤
                '主平': ah_level_h, '主+0.5': ah_plus05_h, 
                '主+1': min(100, ah_plus05_h + 15), 
                '主+2': min(100, ah_plus05_h + 25),
                '主-2': max(0, api_h_win - 30),
                
                '客平': ah_level_a, '客+0.5': ah_plus05_a, 
                '客+1': min(100, ah_plus05_a + 15),
                '客+2': min(100, ah_plus05_a + 25),
                '客-2': max(0, api_a_win - 30),

                '主賠': odds_h, '客賠': odds_a,
                '凱利主': round(kelly_h), '凱利客': round(kelly_a),
                '推介': advice
            }
            
            print(f"         ✅ {h_name} vs {a_name} | API主勝: {api_h_win}% | 賠率: {odds_h}")
            cleaned_data.append(row_data)

    # 上傳
    if cleaned_data:
        df = pd.DataFrame(cleaned_data)
        cols = ['時間','聯賽','主隊','客隊','狀態','主分','客分',
                '主勝率','和局率','客勝率',
                '大0.5','大1.5','大2.5','大3.5',
                'HT0.5','HT1.5','HT2.5',
                '主平','主+0.5','主+1','主+2','主-2',
                '客平','客+0.5','客+1','客+2','客-2',
                '主賠','客賠','凱利主','凱利客','推介']
        
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
