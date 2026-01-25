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
# 優先嘗試 Streamlit Secrets，其次環境變量
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

# ================= 關鍵修復函數 =================
def fix_private_key(key_str):
    """修復 Private Key 的換行問題"""
    if not key_str: return None
    fixed_key = str(key_str).strip().strip("'").strip('"')
    if "\\n" in fixed_key:
        fixed_key = fixed_key.replace("\\n", "\n")
    fixed_key = fixed_key.replace('\\\\n', '\n')
    return fixed_key

def clean_json_string(json_str):
    """
    清洗 JSON 字串：去除前後多餘的引號
    """
    if not json_str: return ""
    clean_str = json_str.strip()
    if clean_str.startswith("'") and clean_str.endswith("'"):
        clean_str = clean_str[1:-1]
    if clean_str.startswith('"') and clean_str.endswith('"') and len(clean_str) > 2 and clean_str[1] == '{':
        clean_str = clean_str[1:-1]
    return clean_str

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

# ================= Google Sheet 連接 =================
def get_google_spreadsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = None
    
    # 1. 嘗試從環境變量 (GitHub Actions / Cloud Run)
    json_text = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
    
    if json_text:
        try:
            print(f"🔍 檢測到環境變量，長度: {len(json_text)}")
            json_text = clean_json_string(json_text)
            
            # === 防呆檢查 ===
            if json_text.startswith("-----BEGIN"):
                print("❌ [嚴重錯誤] 你貼的是 Private Key，不是 JSON！")
                print("💡 請將 GCP_SERVICE_ACCOUNT_JSON 變量改為整個 JSON 檔案的內容 (以 '{' 開頭)。")
                return None

            creds_dict = json.loads(json_text)
            
            if 'private_key' in creds_dict:
                creds_dict['private_key'] = fix_private_key(creds_dict['private_key'])
                
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            print("✅ 環境變量憑證建立成功")
        except json.JSONDecodeError as e:
            print(f"❌ JSON 解析失敗: {e}")
            print(f"⚠️ 讀取到的開頭: {repr(json_text[:20])}...")
        except Exception as e:
            print(f"❌ 環境變量處理失敗: {e}")
    else:
        print("ℹ️ 未檢測到 GCP_SERVICE_ACCOUNT_JSON")

    # 2. 嘗試從 Streamlit Secrets
    if not creds:
        try:
            if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
                creds_dict = dict(st.secrets["gcp_service_account"])
                if 'private_key' in creds_dict:
                    creds_dict['private_key'] = fix_private_key(creds_dict['private_key'])
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                print("✅ Streamlit Secrets 憑證建立成功")
        except Exception as e:
            print(f"❌ Streamlit Secrets 解析失敗: {e}")

    # 3. 本地文件
    if not creds and os.path.exists("key.json"):
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
            print("✅ 本地 key.json 憑證建立成功")
        except Exception:
            pass

    if creds:
        try:
            client = gspread.authorize(creds)
            return client.open(GOOGLE_SHEET_NAME)
        except Exception as e:
            print(f"❌ Google Sheet 連接最終失敗: {e}")
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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 V40.4 防呆修復版 (Connected)")
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
            match_date_str = datetime.fromtimestamp(item['fixture']['timestamp'], pytz.utc).astimezone(hk_tz).strftime('%Y-%m-%d')
            t_str = datetime.fromtimestamp(item['fixture']['timestamp'], pytz.utc).astimezone(hk_tz).strftime('%Y-%m-%d %H:%M')
            status_short = item['fixture']['status']['short']
            
            if status_short in ['FT', 'AET', 'PEN']: status_txt = '完場'
            elif status_short in ['1H', 'HT', '2H', 'LIVE']: status_txt = '進行中'
            elif status_short in ['NS', 'TBD']: status_txt = '未開賽'
            else: status_txt = '延期'

            h_name = item['teams']['home']['name']; a_name = item['teams']['away']['name']
            h_id = item['teams']['home']['id']; a_id = item['teams']['away']['id']
            sc_h = item['goals']['home']; sc_a = item['goals']['away']

            h_info = standings.get(h_id, {'rank': '?', 'form': '?'})
            a_info = standings.get(a_id, {'rank': '?', 'form': '?'})
            
            pred_resp = call_api('predictions', {'fixture': fix_id})
            pred_data = pred_resp['response'][0] if pred_resp and pred_resp.get('response') else None
            
            h_exp, a_exp, src = calculate_split_expected_goals(h_id, a_id, standings, pred_data)
            probs = calculate_advanced_math_probs(h_exp, a_exp)
            
            odds_h, odds_d, odds_a = 0,0,0
            if status_txt != '完場':
                odds_h, odds_d, odds_a = get_best_odds(fix_id)
            
            h2h_h, h2h_d, h2h_a = get_h2h_stats(h_id, a_id)

            val_h = ""; val_d = ""; val_a = ""
            if odds_h > 0 and (probs['h_win']/100) > (1/odds_h): val_h = "💰"
            if odds_d > 0 and (probs['draw']/100) > (1/odds_d): val_d = "💰"
            if odds_a > 0 and (probs['a_win']/100) > (1/odds_a): val_a = "💰"

            cleaned_data.append({
                '日期': match_date_str, 
                '時間': t_str, '聯賽': lg_name, '主隊': h_name, '客隊': a_name, '狀態': status_txt,
                '主分': sc_h if sc_h is not None else "", '客分': sc_a if sc_a is not None else "",
                '主排名': h_info['rank'], '客排名': a_info['rank'],
                '主Value': val_h, '和Value': val_d, '客Value': val_a,
                'xG主': round(h_exp,2), 'xG客': round(a_exp,2), '數據源': src,
                '主勝率': round(probs['h_win']), '和率': round(probs['draw']), '客勝率': round(probs['a_win']),
                '大0.5': round(probs['o05']), 
                '大1.5': round(probs['o15']),
                '大2.5': round(probs['o25']), 
                '大3.5': round(probs['o35']),
                '半大0.5': round(probs['ht_o05']),
                '半大1.5': round(probs['ht_o15']),
                '亞盤主': probs['ah_data']['h_pick'],
                '亞盤主率': round(probs['ah_data']['h_prob']),
                '亞盤客': probs['ah_data']['a_pick'],
                '亞盤客率': round(probs['ah_data']['a_prob']),
                'BTTS': round(probs['btts']),
                '主賠': odds_h, '和賠': odds_d, '客賠': odds_a,
                'H2H主': h2h_h, 'H2H和': h2h_d, 'H2H客': h2h_a
            })
            
            print(f"         ✅ {h_name} vs {a_name}")
            time.sleep(0.1)

    if cleaned_data:
        df = pd.DataFrame(cleaned_data)
        try:
            df.to_csv(CSV_FILENAME, index=False, encoding='utf-8-sig')
            print(f"\n💾 數據已儲存: {CSV_FILENAME}")
        except Exception as e: print(f"❌ CSV 錯誤: {e}")

        spreadsheet = get_google_spreadsheet()
        if spreadsheet:
            try:
                spreadsheet.sheet1.clear()
                spreadsheet.sheet1.update(range_name='A1', values=[df.columns.values.tolist()] + df.astype(str).values.tolist())
                print("☁️ Google Cloud 上傳完成")
            except Exception as e: 
                print(f"⚠️ 上傳雲端失敗: {e}")
        else:
            print("💻 本地模式 (未連接 Google Sheet 或 缺少憑證)")
    else:
        print("⚠️ 無數據")

if __name__ == "__main__":
    main()
