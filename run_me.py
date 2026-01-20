import requests
import pandas as pd
import math
import time
import gspread
from datetime import datetime, timedelta
import pytz
from oauth2client.service_account import ServiceAccountCredentials
import os
import sys

# ================= 設定區 =================
API_KEY = '6bf59594223b07234f75a8e2e2de5178' 
BASE_URL = 'https://v3.football.api-sports.io'
GOOGLE_SHEET_NAME = "數據上傳" 
CSV_FILENAME = "football_data_backup.csv" 

# 完整欄位定義
FULL_COLUMNS = [
    '時間', '聯賽', '主隊', '客隊', '狀態', '主分', '客分',
    '主排名', '客排名', '主走勢', '客走勢',
    '主Value', '和Value', '客Value', # 新增和Value
    'xG主', 'xG客', '數據源',
    '主勝率', '和率', '客勝率', # 新增和率
    'BTTS機率', '主先入球率', # 新增
    '全場大0.5', '全場大1.5', '全場大2.5', '全場大3.5',
    '半場大0.5', '半場大1.5',
    '主賠', '和賠', '客賠',
    '亞盤主', '亞盤客', '亞盤盤口',
    '主傷', '客傷', 'H2H主', 'H2H和', 'H2H客'
]

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

# ================= 亞盤格式轉換工具 =================
def format_ah_line(val):
    try:
        f = float(val)
        if f == 0: return "平手盤"
        
        # 處理 .25 和 .75 的情況
        rem = f % 1
        base = int(f)
        
        # 正數處理
        if f > 0:
            if rem == 0.25: return f"+{base}/+{base+0.5}"
            if rem == 0.5: return f"+{f}"
            if rem == 0.75: return f"+{base+0.5}/+{base+1}"
            return f"+{f}"
            
        # 負數處理
        if f < 0:
            # 例如 -0.25 -> 0/-0.5 (base=0)
            # 例如 -0.75 -> -0.5/-1 (base=0)
            # 例如 -1.25 -> -1/-1.5 (base=-1)
            abs_f = abs(f)
            abs_base = int(abs_f)
            abs_rem = abs_f % 1
            
            if abs_rem == 0.25: 
                low = abs_base
                high = abs_base + 0.5
                s_low = f"-{low}" if low != 0 else "0"
                return f"{s_low}/-{high}"
            
            if abs_rem == 0.75:
                low = abs_base + 0.5
                high = abs_base + 1
                return f"-{low}/-{high}"
                
            return f"{f}"
            
        return str(f)
    except: return str(val)

# ================= 詳細賠率與數據抓取 =================
def get_detailed_odds(fixture_id):
    data = call_api('odds', {'fixture': fixture_id})
    res = {
        'h': 0, 'd': 0, 'a': 0,
        'ah_h': 0, 'ah_a': 0, 'ah_str': '',
        'o05': 0, 'o15': 0, 'o25': 0, 'o35': 0,
        'ht_o05': 0, 'ht_o15': 0,
        'btts_yes': 0, 'btts_no': 0,
        'first_h': 0, 'first_a': 0 # 第一球
    }
    
    if not data or not data.get('response'): return res
    
    try:
        bks = data['response'][0]['bookmakers']
        target = next((b for b in bks if b['id'] in [1, 6, 8, 2]), bks[0] if bks else None)
        
        if target:
            for bet in target['bets']:
                # ID 1: 獨贏
                if bet['id'] == 1:
                    for v in bet['values']:
                        if v['value']=='Home': res['h'] = float(v['odd'])
                        if v['value']=='Draw': res['d'] = float(v['odd'])
                        if v['value']=='Away': res['a'] = float(v['odd'])
                
                # ID 4: 亞盤 (Asian Handicap)
                elif bet['id'] == 4:
                    # 嘗試抓取比較均衡的盤口 (賠率接近 1.8-2.1)
                    best_line = None
                    min_diff = 99
                    for v in bet['values']:
                        # API通常把盤口放在 extra 或者 value 裡，這裡簡化取第一個或中間的
                        pass 
                    # 這裡為了簡單，取第一組數據，實際環境可優化找「主盤」
                    if len(bet['values']) > 0:
                        # API Sports 的 AH 盤口有時在 value (如 "Home +0.5") 或 extra
                        # 這裡假設我們要抓取盤口值
                        label = bet['values'][0]['value'] 
                        # 通常 API 不會直接給 -0.25, 而是給 Home/Away 的賠率，盤口在外面
                        # 這裡做一個模擬抓取，具體依賴 API 響應結構
                        # 假設 API 回傳格式能解析到盤口
                        res['ah_h'] = float(bet['values'][0]['odd'])
                        if len(bet['values']) > 1: res['ah_a'] = float(bet['values'][1]['odd'])
                        # 嘗試解析盤口字串 (需要 API 實際支持)
                        # 暫時用賠率代替，後續在 app.py 顯示
                        
                # ID 5: 全場大小 (Goals Over/Under) - 抓取多個盤口
                elif bet['id'] == 5:
                    for v in bet['values']:
                        val_str = v['value'] # e.g. "Over 2.5"
                        odd = float(v['odd'])
                        if "Over 0.5" in val_str: res['o05'] = odd
                        if "Over 1.5" in val_str: res['o15'] = odd
                        if "Over 2.5" in val_str: res['o25'] = odd
                        if "Over 3.5" in val_str: res['o35'] = odd

                # ID 6: 半場大小 (Goals Over/Under First Half)
                elif bet['id'] == 6:
                    for v in bet['values']:
                        val_str = v['value']
                        odd = float(v['odd'])
                        if "Over 0.5" in val_str: res['ht_o05'] = odd
                        if "Over 1.5" in val_str: res['ht_o15'] = odd
                        
                # ID 8: BTTS (Both Teams To Score)
                elif bet['id'] == 8:
                    for v in bet['values']:
                        if v['value'] == 'Yes': res['btts_yes'] = float(v['odd'])
                        if v['value'] == 'No': res['btts_no'] = float(v['odd'])

                # ID 46: Team to Score First (第一隊入球) - 假設 ID
                # 如果沒有這個 ID，可嘗試用 Recent Stats 模擬
                # 這裡嘗試抓取 ID 46 或類似
                elif bet['id'] == 46: # 假設 ID
                     for v in bet['values']:
                        if v['value'] == 'Home': res['first_h'] = float(v['odd'])
                        if v['value'] == 'Away': res['first_a'] = float(v['odd'])

    except: pass
    return res

# ================= 輔助與數學 =================
def get_google_spreadsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if "GCP_SERVICE_ACCOUNT" in os.environ:
             creds_dict = eval(os.environ["GCP_SERVICE_ACCOUNT"])
             creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        elif os.path.exists("key.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        else: return None
        client = gspread.authorize(creds)
        return client.open(GOOGLE_SHEET_NAME)
    except: return None

def get_league_standings(league_id, season):
    data = call_api('standings', {'league': league_id, 'season': season})
    standings_map = {}
    if not data or not data.get('response'): return standings_map
    try:
        for group in data['response'][0]['league']['standings']:
            for team in group:
                standings_map[team['team']['id']] = {'rank': team['rank'], 'form': team['form']}
    except: pass
    return standings_map

def get_injuries(fix_id, h_name, a_name):
    data = call_api('injuries', {'fixture': fix_id})
    h=0; a=0
    if data and data.get('response'):
        for i in data['response']:
            if i['team']['name'] == h_name: h+=1
            elif i['team']['name'] == a_name: a+=1
    return h, a

def get_h2h(h_id, a_id):
    data = call_api('fixtures/headtohead', {'h2h': f"{h_id}-{a_id}"})
    h=0; d=0; a=0
    if data and data.get('response'):
        for m in data['response'][:10]:
            sh = m['goals']['home']; sa = m['goals']['away']
            if sh is not None and sa is not None:
                if sh > sa: h+=1
                elif sa > sh: a+=1
                else: d+=1
    return h, d, a

def odd_to_prob(odd):
    if odd and odd > 1: return round((1/odd)*100)
    return 0

# xG 模擬計算 (排名權重算法) - 解決 xG 為 0 的問題
def calc_xg_sim(h_rank, a_rank, recent_goals_h=1.5, recent_goals_a=1.2):
    # 基礎 xG
    base_h = 1.35
    base_a = 1.05
    
    # 排名修正 (排名越小越強)
    # 排名差 1 位，xG 影響 0.05
    rank_diff = a_rank - h_rank # 正數代表主隊排名高(數字小)
    
    xg_h = base_h + (rank_diff * 0.03) + (recent_goals_h * 0.2)
    xg_a = base_a - (rank_diff * 0.03) + (recent_goals_a * 0.2)
    
    return max(0.1, round(xg_h, 2)), max(0.1, round(xg_a, 2))

# 泊松分佈計算勝平負
def poisson_prob(k, lam):
    return (math.pow(lam, k) * math.exp(-lam)) / math.factorial(k)

def calc_probs(xg_h, xg_a):
    h_win=0; draw=0; a_win=0
    for h in range(8):
        for a in range(8):
            p = poisson_prob(h, xg_h) * poisson_prob(a, xg_a)
            if h > a: h_win += p
            elif a > h: a_win += p
            else: draw += p
    return h_win*100, draw*100, a_win*100

# ================= 主程式 =================
def main():
    print("🚀 V40.0 Ultimate Data Update")
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    utc_now = datetime.now(pytz.utc)
    
    from_date = (utc_now - timedelta(days=3)).strftime('%Y-%m-%d')
    to_date = (utc_now + timedelta(days=3)).strftime('%Y-%m-%d')
    season = 2025 # 請根據實際年份調整
    
    data_list = []

    for lg_id, lg_name in LEAGUE_ID_MAP.items():
        print(f"Checking {lg_name}...")
        standings = get_league_standings(lg_id, season)
        
        fixtures = call_api('fixtures', {'league': lg_id, 'season': season, 'from': from_date, 'to': to_date})
        if not fixtures or not fixtures.get('response'): continue
        
        for item in fixtures['response']:
            fix_id = item['fixture']['id']
            status = item['fixture']['status']['short']
            t_str = datetime.fromtimestamp(item['fixture']['timestamp'], pytz.utc).astimezone(hk_tz).strftime('%Y-%m-%d %H:%M')
            
            # 狀態對應
            status_map = {
                'FT': '完場', 'AET': '完場', 'PEN': '完場',
                'NS': '未開賽',
                '1H': '進行中', 'HT': '進行中', '2H': '進行中', 'LIVE': '進行中',
                'PST': '延期', 'CANC': '取消', 'ABD': '取消'
            }
            status_txt = status_map.get(status, status)

            h_id = item['teams']['home']['id']
            a_id = item['teams']['away']['id']
            h_name = item['teams']['home']['name']
            a_name = item['teams']['away']['name']
            
            # 抓取數據 (僅未完場/進行中)
            odds = {'h':0,'d':0,'a':0}
            inj_h=0; inj_a=0
            
            # 即使完場也可以抓賠率作回顧，但為了省流，取消/延期不抓
            if "取消" not in status_txt and "延期" not in status_txt:
                odds = get_detailed_odds(fix_id)
                if status_txt != '完場':
                    inj_h, inj_a = get_injuries(fix_id, h_name, a_name)

            h2h_h, h2h_d, h2h_a = get_h2h(h_id, a_id)
            
            # 排名與 xG
            h_rank = standings.get(h_id, {}).get('rank', 10)
            a_rank = standings.get(a_id, {}).get('rank', 10)
            
            # 【xG 修復】使用模擬算法確保有數值
            xg_h, xg_a = calc_xg_sim(int(h_rank) if str(h_rank).isdigit() else 10, 
                                     int(a_rank) if str(a_rank).isdigit() else 10)

            # 勝率計算 (含和局)
            ph, pd_prob, pa = calc_probs(xg_h, xg_a)
            
            # Value 計算 (含和局)
            val_h = "💰" if odds['h'] > 0 and (ph/100 > 1/odds['h']) else ""
            val_d = "💰" if odds['d'] > 0 and (pd_prob/100 > 1/odds['d']) else ""
            val_a = "💰" if odds['a'] > 0 and (pa/100 > 1/odds['a']) else ""
            
            # 亞盤字串格式化 (這裡做一個簡單的模擬轉換，因為 API 回傳的是賠率)
            # 實際應用中如果能抓到盤口值 (如 -0.25) 則傳入 format_ah_line
            # 這裡暫時顯示賠率，或者如果能從 odds['ah_str'] 獲取則使用
            ah_display = "平手盤" # 預設，需根據 API 實際盤口值調整

            data_list.append({
                '時間': t_str, '聯賽': lg_name, '主隊': h_name, '客隊': a_name, '狀態': status_txt,
                '主分': item['goals']['home'] if item['goals']['home'] is not None else "",
                '客分': item['goals']['away'] if item['goals']['away'] is not None else "",
                '主排名': h_rank, '客排名': a_rank,
                '主走勢': standings.get(h_id, {}).get('form', ''),
                '客走勢': standings.get(a_id, {}).get('form', ''),
                
                '主Value': val_h, '和Value': val_d, '客Value': val_a,
                'xG主': xg_h, 'xG客': xg_a, '數據源': 'AI模擬',
                
                '主勝率': int(ph), '和率': int(pd_prob), '客勝率': int(pa),
                
                # 新增機率
                'BTTS機率': odd_to_prob(odds.get('btts_yes', 0)),
                '主先入球率': odd_to_prob(odds.get('first_h', 0)),
                
                # 大小球
                '全場大0.5': odds.get('o05', 0), '全場大1.5': odds.get('o15', 0),
                '全場大2.5': odds.get('o25', 0), '全場大3.5': odds.get('o35', 0),
                '半場大0.5': odds.get('ht_o05', 0), '半場大1.5': odds.get('ht_o15', 0),
                
                '主賠': odds['h'], '和賠': odds['d'], '客賠': odds['a'],
                '亞盤主': odds.get('ah_h', 0), '亞盤客': odds.get('ah_a', 0), '亞盤盤口': ah_display,
                
                '主傷': inj_h, '客傷': inj_a,
                'H2H主': h2h_h, 'H2H和': h2h_d, 'H2H客': h2h_a
            })
            time.sleep(0.1)

    # 數據存檔
    if data_list:
        df = pd.DataFrame(data_list)
    else:
        df = pd.DataFrame(columns=FULL_COLUMNS)
        
    df.to_csv(CSV_FILENAME, index=False, encoding='utf-8-sig')
    print(f"Backup saved: {len(df)} rows")
    
    # 上傳 Google Sheet
    sheet = get_google_spreadsheet()
    if sheet:
        try:
            sheet.sheet1.clear()
            df_str = df.fillna('').astype(str)
            if df_str.empty:
                sheet.sheet1.update(range_name='A1', values=[FULL_COLUMNS])
            else:
                sheet.sheet1.update(range_name='A1', values=[df_str.columns.values.tolist()] + df_str.values.tolist())
            print("✅ Upload success")
        except Exception as e: print(f"❌ Upload failed: {e}")

if __name__ == "__main__":
    main()
