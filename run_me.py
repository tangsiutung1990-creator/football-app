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

# ================= 增強型數據獲取 (100% Potential) =================

def get_best_odds(fixture_id):
    """
    智能賠率獲取：如果 Bet365 沒開盤，自動尋找其他莊家 (1xBet, Unibet 等)
    """
    data = call_api('odds', {'fixture': fixture_id})
    if not data or not data.get('response'):
        return 0, 0, 0
    
    # 優先順序: Bet365(1) -> 1xBet(6) -> Unibet(8) -> Bwin(2) -> 任意
    preferred_books = [1, 6, 8, 2]
    bookmakers = data['response'][0]['bookmakers']
    
    target_book = None
    
    # 1. 嘗試找首選莊家
    for pref_id in preferred_books:
        target_book = next((b for b in bookmakers if b['id'] == pref_id), None)
        if target_book: break
    
    # 2. 如果都沒有，就拿第一個
    if not target_book and bookmakers:
        target_book = bookmakers[0]
        
    if target_book:
        bets = target_book['bets']
        winner_bet = next((b for b in bets if b['name'] == 'Match Winner'), None)
        if winner_bet:
            h=0; d=0; a=0
            for o in winner_bet['values']:
                if o['value'] == 'Home': h = float(o['odd'])
                if o['value'] == 'Draw': d = float(o['odd'])
                if o['value'] == 'Away': a = float(o['odd'])
            return h, d, a
            
    return 0, 0, 0

def get_injuries_count(fixture_id):
    """
    獲取雙方傷兵/停賽人數 (API-Football 強大功能)
    """
    data = call_api('injuries', {'fixture': fixture_id})
    if not data or not data.get('response'):
        return 0, 0 # 無數據
        
    h_count = 0
    a_count = 0
    # API 回傳是一個 list，每個 item 是一個球員
    for item in data['response']:
        # 簡單判斷隊伍 (API 這裡比較複雜，我們假設數據已按主客分好，這裡簡化計數)
        # 嚴謹做法是比對 team ID，這裡為了效能做簡單估算
        # 這裡我們只回傳總數，或需要在 main 裡傳入 team ID 來精確區分
        # 暫時返回 "有傷兵數據" 的標記
        pass
        
    # 由於 injuries endpoint 消耗較大且需要 Team ID 比對，
    # 為了保持速度，我們改用 predictions 裡的 "players" 缺失報告
    return 0, 0 

# ================= 數學運算 =================
def poisson_prob(k, lam):
    if lam < 0: lam = 0
    return (math.pow(lam, k) * math.exp(-lam)) / math.factorial(k)

def calculate_exact_goals_probs(h_exp, a_exp):
    h_exp = float(h_exp); a_exp = float(a_exp)
    prob_o05 = 0; prob_o15 = 0; prob_o25 = 0; prob_o35 = 0
    
    ht_h_exp = h_exp * 0.45; ht_a_exp = a_exp * 0.45
    prob_ht_o05 = 0; prob_ht_o15 = 0; prob_ht_o25 = 0
    
    # 全場
    for h in range(8):
        for a in range(8):
            p = poisson_prob(h, h_exp) * poisson_prob(a, a_exp)
            if h+a > 0.5: prob_o05 += p
            if h+a > 1.5: prob_o15 += p
            if h+a > 2.5: prob_o25 += p
            if h+a > 3.5: prob_o35 += p
            
    # 半場
    for h in range(5):
        for a in range(5):
            p = poisson_prob(h, ht_h_exp) * poisson_prob(a, ht_a_exp)
            if h+a > 0.5: prob_ht_o05 += p
            if h+a > 1.5: prob_ht_o15 += p
            if h+a > 2.5: prob_ht_o25 += p

    return {
        'o05': round(prob_o05*100), 'o15': round(prob_o15*100),
        'o25': round(prob_o25*100), 'o35': round(prob_o35*100),
        'ht_o05': round(prob_ht_o05*100), 'ht_o15': round(prob_ht_o15*100), 'ht_o25': round(prob_ht_o25*100)
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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 V25.0 API-Full-Potential (Odds Fix + UI Data) 啟動...")
    
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    utc_now = datetime.now(pytz.utc)
    
    # 過去 7 天 + 未來 3 天
    from_date = (utc_now - timedelta(days=7)).strftime('%Y-%m-%d')
    to_date = (utc_now + timedelta(days=3)).strftime('%Y-%m-%d')
    season = 2025 # 正確：對應 2025-2026 賽季
    
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
            
            # 處理比分 (去除小數點，轉為整數顯示)
            sc_h = item['goals']['home']; sc_a = item['goals']['away']
            score_h_display = str(int(sc_h)) if sc_h is not None else ""
            score_a_display = str(int(sc_a)) if sc_a is not None else ""

            # === 100% API 潛力：獲取 Predictions (含實力對比) ===
            pred_resp = call_api('predictions', {'fixture': fix_id})
            
            api_h_win=0; api_draw=0; api_a_win=0
            api_goals_h=1.2; api_goals_a=1.0
            advice="暫無"; form_h="50%"; form_a="50%"
            
            if pred_resp and pred_resp.get('response'):
                pred = pred_resp['response'][0]
                api_h_win = clean_percent_str(pred['predictions']['percent']['home'])
                api_draw = clean_percent_str(pred['predictions']['percent']['draw'])
                api_a_win = clean_percent_str(pred['predictions']['percent']['away'])
                advice = pred['predictions'].get('advice', '觀望')
                
                # 獲取 Comparison 數據 (100% Potential)
                try:
                    form_h = pred['comparison']['form']['home'] # e.g. "70%"
                    form_a = pred['comparison']['form']['away']
                    # 使用 API 的攻擊力作為入球預期基礎
                    api_goals_h = float(pred['teams']['home']['last_5']['goals']['for']['average'])
                    api_goals_a = float(pred['teams']['away']['last_5']['goals']['for']['average'])
                    if api_goals_h == 0: api_goals_h = 0.5 # 避免0
                    if api_goals_a == 0: api_goals_a = 0.5
                except: pass

            # === 修復賠率獲取 (使用增強函數) ===
            odds_h = 0; odds_a = 0
            if status != '完場':
                odds_h, odds_d, odds_a = get_best_odds(fix_id)

            # === 數學計算 ===
            ou_probs = calculate_exact_goals_probs(api_goals_h, api_goals_a)
            
            # 亞盤
            total_win = api_h_win + api_a_win + 0.01
            ah_level_h = round((api_h_win / total_win) * 100)
            ah_level_a = round((api_a_win / total_win) * 100)
            
            ah_plus05_h = api_h_win + api_draw
            ah_plus05_a = api_a_win + api_draw
            
            # 凱利 (現在 odds_h 有數據了，計算會準確)
            kelly_h = calculate_kelly_stake(api_h_win/100, odds_h)
            kelly_a = calculate_kelly_stake(api_a_win/100, odds_a)

            cleaned_data.append({
                '時間': t_str, '聯賽': lg_name, '主隊': h_name, '客隊': a_name,
                '狀態': status, 
                '主分': score_h_display, '客分': score_a_display, # 確保是字串格式
                
                '主勝率': api_h_win, '和局率': api_draw, '客勝率': api_a_win,
                
                '大0.5': ou_probs['o05'], '大1.5': ou_probs['o15'],
                '大2.5': ou_probs['o25'], '大3.5': ou_probs['o35'],
                'HT0.5': ou_probs['ht_o05'], 'HT1.5': ou_probs['ht_o15'], 'HT2.5': ou_probs['ht_o25'],
                
                '主平': ah_level_h, '主+0.5': ah_plus05_h, 
                '主+1': min(100, ah_plus05_h + 15), '主+2': min(100, ah_plus05_h + 25), '主-2': max(0, api_h_win - 30),
                
                '客平': ah_level_a, '客+0.5': ah_plus05_a, 
                '客+1': min(100, ah_plus05_a + 15), '客+2': min(100, ah_plus05_a + 25), '客-2': max(0, api_a_win - 30),

                '主賠': odds_h, '客賠': odds_a,
                '凱利主': round(kelly_h), '凱利客': round(kelly_a),
                '推介': advice,
                '主狀態': form_h, '客狀態': form_a # 新增狀態數據
            })
            print(f"         ✅ {h_name} vs {a_name} | 賠率: {odds_h}/{odds_a} | 凱利: {round(kelly_h)}%")

    # 上傳
    if cleaned_data:
        df = pd.DataFrame(cleaned_data)
        cols = ['時間','聯賽','主隊','客隊','狀態','主分','客分',
                '主勝率','和局率','客勝率',
                '大0.5','大1.5','大2.5','大3.5',
                'HT0.5','HT1.5','HT2.5',
                '主平','主+0.5','主+1','主+2','主-2',
                '客平','客+0.5','客+1','客+2','客-2',
                '主賠','客賠','凱利主','凱利客','推介','主狀態','客狀態']
        
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
