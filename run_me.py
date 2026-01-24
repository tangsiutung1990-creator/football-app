import requests
import pandas as pd
import math
import time
import gspread
from datetime import datetime, timedelta
import pytz
from oauth2client.service_account import ServiceAccountCredentials
import os
import streamlit as st
import json

# ================= 設定區 =================
# 嘗試讀取 API KEY
API_KEY = None
try:
    if hasattr(st, "secrets") and "api" in st.secrets and "key" in st.secrets["api"]:
        API_KEY = st.secrets["api"]["key"]
except Exception:
    pass 

if not API_KEY:
    API_KEY = os.getenv("FOOTBALL_API_KEY")

BASE_URL = 'https://v3.football.api-sports.io'
GOOGLE_SHEET_NAME = "數據上傳" 
CSV_FILENAME = "football_data_backup.csv" 

LEAGUE_ID_MAP = {
    39: '英超', 40: '英冠', 41: '英甲', 140: '西甲', 141: '西乙',
    135: '意甲', 78: '德甲', 61: '法甲', 88: '荷甲', 94: '葡超',
    144: '比甲', 179: '蘇超', 203: '土超', 119: '丹超', 113: '瑞典超',
    103: '挪超', 98: '日職', 292: '韓K1', 188: '澳職', 253: '美職',
    262: '墨超', 71: '巴甲', 128: '阿甲', 265: '智甲',
    2: '歐聯', 3: '歐霸'
}

# ================= 輔助函數：修復 Private Key =================
def fix_private_key(key_str):
    """修復 private_key 中的換行符問題"""
    if not key_str: return key_str
    # 將 literal 的 \n 替換為真正的換行符
    fixed_key = key_str.replace('\\n', '\n')
    # 確保頭尾沒有多餘的引號或空白
    return fixed_key.strip().strip('"').strip("'")

# ================= API 連接 =================
def call_api(endpoint, params=None):
    if not API_KEY: return None
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-apisports-key': API_KEY}
    url = f"{BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("errors") and isinstance(data['errors'], list) and len(data['errors']) > 0: return None
            return data
        elif response.status_code == 429:
            time.sleep(5)
            return None
        else: return None
    except: return None

# ================= Google Sheet 連接 (JWT Fix) =================
def get_google_spreadsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = None
    
    # 1. 嘗試從環境變量 (GitHub Actions / Cloud Run 優先)
    json_text = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
    if json_text:
        try:
            creds_dict = json.loads(json_text)
            # CRITICAL FIX: 強制修復 Private Key
            if 'private_key' in creds_dict:
                creds_dict['private_key'] = fix_private_key(creds_dict['private_key'])
            
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        except Exception as e:
            print(f"⚠️ GCP_SERVICE_ACCOUNT_JSON 解析失敗: {e}")
    else:
        print("ℹ️ 未檢測到 GCP_SERVICE_ACCOUNT_JSON 環境變量")

    # 2. 嘗試從 Streamlit Secrets (Streamlit Cloud)
    if not creds:
        try:
            if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
                # 必須轉為標準 dict
                creds_dict = dict(st.secrets["gcp_service_account"])
                if 'private_key' in creds_dict:
                    creds_dict['private_key'] = fix_private_key(creds_dict['private_key'])
                
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        except Exception:
            pass

    # 3. 嘗試從本地文件 (Local Dev)
    if not creds and os.path.exists("key.json"):
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        except Exception as e:
            print(f"⚠️ key.json 讀取失敗: {e}")

    if creds:
        try:
            client = gspread.authorize(creds)
            return client.open(GOOGLE_SHEET_NAME)
        except Exception as e:
            print(f"⚠️ Google Sheet 連接異常 (可能為權限或 Key 錯誤): {e}")
            return None
    
    return None

# ================= 數據與數學核心 =================
def get_league_standings(league_id, season):
    data = call_api('standings', {'league': league_id, 'season': season})
    standings_map = {}
    if not data or not data.get('response'): return standings_map
    try:
        for group in data['response'][0]['league']['standings']:
            for team in group:
                t_id = team['team']['id']
                h_s = team['home']; a_s = team['away']
                standings_map[t_id] = {
                    'rank': team['rank'], 'form': team['form'],
                    'home_stats': {'played': h_s['played'], 'avg_goals_for': h_s['goals']['for']/(h_s['played'] or 1), 'avg_goals_against': h_s['goals']['against']/(h_s['played'] or 1)},
                    'away_stats': {'played': a_s['played'], 'avg_goals_for': a_s['goals']['for']/(a_s['played'] or 1), 'avg_goals_against': a_s['goals']['against']/(a_s['played'] or 1)}
                }
    except: pass
    return standings_map

def get_h2h_stats(h_id, a_id):
    data = call_api('fixtures/headtohead', {'h2h': f"{h_id}-{a_id}"})
    if not data or not data.get('response'): return 0, 0, 0
    h=0; d=0; a=0
    for m in data['response'][:10]:
        sc_h = m['goals']['home']; sc_a = m['goals']['away']
        if sc_h is None or sc_a is None: continue
        if sc_h > sc_a: h+=1
        elif sc_a > sc_h: a+=1
        else: d+=1
    return h, d, a

def get_best_odds(fixture_id):
    data = call_api('odds', {'fixture': fixture_id})
    if not data or not data.get('response'): return 0, 0, 0
    try:
        bks = data['response'][0]['bookmakers']
        target = next((b for b in bks if b['id'] in [1, 6, 8, 2]), bks[0] if bks else None)
        if target:
            bet = next((b for b in target['bets'] if b['name'] == 'Match Winner'), None)
            if bet:
                h=0; d=0; a=0
                for o in bet['values']:
                    if o['value'] == 'Home': h = float(o['odd'])
                    if o['value'] == 'Draw': d = float(o['odd'])
                    if o['value'] == 'Away': a = float(o['odd'])
                return h, d, a
    except: pass
    return 0, 0, 0

def safe_float(val):
    try: return float(val) if val is not None else 0.0
    except: return 0.0

def calculate_split_expected_goals(h_id, a_id, standings_map, pred_data):
    api_h = 1.3; api_a = 1.0
    if pred_data:
        t = pred_data.get('teams', {})
        api_h = safe_float(t.get('home',{}).get('last_5',{}).get('goals',{}).get('for',{}).get('average'))
        api_a = safe_float(t.get('away',{}).get('last_5',{}).get('goals',{}).get('for',{}).get('average'))
    
    split_h = 0; split_a = 0; has_split = False
    h_stats = standings_map.get(h_id, {})
    a_stats = standings_map.get(a_id, {})
    
    if h_stats and a_stats:
        try:
            if h_stats['home_stats']['played'] > 2 and a_stats['away_stats']['played'] > 2:
                split_h = (h_stats['home_stats']['avg_goals_for'] + a_stats['away_stats']['avg_goals_against']) / 2.0
                split_a = (a_stats['away_stats']['avg_goals_for'] + h_stats['home_stats']['avg_goals_against']) / 2.0
                has_split = True
        except: pass
    
    if has_split:
        fh = max(0.1, (split_h * 0.7) + (api_h * 0.3))
        fa = max(0.1, (split_a * 0.7) + (api_a * 0.3))
        return fh, fa, "特化數據"
    return max(0.1, api_h), max(0.1, api_a), "API數據"

def poisson_prob(k, lam):
    if lam <= 0: return 0
    return (math.pow(lam, k) * math.exp(-lam)) / math.factorial(k)

def calculate_asian_handicap_data(h_xg, a_xg, prob_exact):
    diff = h_xg - a_xg
    line = 0.0
    if diff >= 1.8: line = -1.5
    elif diff >= 1.3: line = -1.0
    elif diff >= 0.8: line = -0.5
    elif diff >= 0.3: line = -0.25
    elif diff > -0.3: line = 0.0
    elif diff > -0.8: line = 0.25
    elif diff > -1.3: line = 0.5
    elif diff > -1.8: line = 1.0
    else: line = 1.5

    h_win_prob = 0
    a_win_prob = 0
    
    for (h, a), prob in prob_exact.items():
        if (h + line) > a: h_win_prob += prob
        elif (h + line) == a: h_win_prob += (prob * 0.5) 
        if (a - line) > h: a_win_prob += prob
    
    h_sign = "+" if line > 0 else "" 
    h_line_str = f"{h_sign}{line}"
    if line == 0: h_line_str = "0"
    
    a_line = -line
    a_sign = "+" if a_line > 0 else ""
    a_line_str = f"{a_sign}{a_line}"
    if a_line == 0: a_line_str = "0"

    return {
        'h_pick': f"主 {h_line_str}",
        'h_prob': h_win_prob * 100,
        'a_pick': f"客 {a_line_str}",
        'a_prob': a_win_prob * 100
    }

def calculate_advanced_math_probs(h_exp, a_exp):
    prob_exact = {}
    for h in range(10):
        for a in range(10): prob_exact[(h, a)] = poisson_prob(h, h_exp) * poisson_prob(a, a_exp)
    
    h_win = sum(p for (h, a), p in prob_exact.items() if h > a)
    a_win = sum(p for (h, a), p in prob_exact.items() if a > h)
    draw = sum(p for (h, a), p in prob_exact.items() if h == a)
    
    o05 = sum(p for (h, a), p in prob_exact.items() if h+a > 0.5)
    o15 = sum(p for (h, a), p in prob_exact.items() if h+a > 1.5)
    o25 = sum(p for (h, a), p in prob_exact.items() if h+a > 2.5)
    o35 = sum(p for (h, a), p in prob_exact.items() if h+a > 3.5)
    btts = 1 - sum(p for (h, a), p in prob_exact.items() if h==0 or a==0)

    ht_h_exp = h_exp * 0.40; ht_a_exp = a_exp * 0.40 
    ht_prob_exact = {}
    for h in range(6):
        for a in range(6): ht_prob_exact[(h, a)] = poisson_prob(h, ht_h_exp) * poisson_prob(a, ht_a_exp)
    
    ht_o05 = sum(p for (h, a), p in ht_prob_exact.items() if h+a > 0.5)
    ht_o15 = sum(p for (h, a), p in ht_prob_exact.items() if h+a > 1.5)

    ah_data = calculate_asian_handicap_data(h_exp, a_exp, prob_exact)

    return {
        'h_win': h_win*100, 'draw': draw*100, 'a_win': a_win*100,
        'o05': o05*100, 'o15': o15*100, 'o25': o25*100, 'o35': o35*100,
        'ht_o05': ht_o05*100, 'ht_o15': ht_o15*100,
        'btts': btts*100,
        'ah_data': ah_data
    }

# ================= 主流程 =================
def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 V38.9 數據引擎啟動 (Key Fix)")
    if not API_KEY: print("⚠️ 警告: 缺少 API Key")

    hk_tz = pytz.timezone('Asia/Hong_Kong')
    hk_now = datetime.now(hk_tz)
    
    yesterday_str = (hk_now - timedelta(days=1)).strftime('%Y-%m-%d')
    today_str = (hk_now + timedelta(days=2)).strftime('%Y-%m-%d')
    season = 2025
    
    print(f"📅 掃描: {yesterday_str} 至 {today_str}")
    cleaned_data = []

    for lg_id, lg_name in LEAGUE_ID_MAP.items():
        standings = get_league_standings(lg_id, season)
        fixtures_data = call_api('fixtures', {'league': lg_id, 'season': season, 'from': yesterday_str, 'to': today_str})
        
        if not fixtures_data or not fixtures_data.get('response'): continue
        fixtures = fixtures_data['response']
        print(f"   ⚽ {lg_name}: {len(fixtures)} 場")
        
        for item in fixtures:
            fix_id = item['fixture']['id']
            match_date_str = datetime.fromtimestamp(item['fixture']['timestamp'], pytz.utc).astimezone(hk
