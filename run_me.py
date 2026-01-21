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
import streamlit as st

# ================= 設定區 =================
# API Key 獲取順序: 1. Streamlit Secrets  2. 環境變數
API_KEY = None

# 嘗試從 Streamlit Secrets 讀取
try:
    if "api" in st.secrets and "key" in st.secrets["api"]:
        API_KEY = st.secrets["api"]["key"]
except FileNotFoundError:
    pass # 本地運行且沒有 .streamlit/secrets.toml 時會報錯，忽略

# 如果 Secrets 沒讀到，嘗試環境變數
if not API_KEY:
    API_KEY = os.getenv("FOOTBALL_API_KEY")

if not API_KEY:
    print("❌ 錯誤: 未找到 API Key。請配置 .streamlit/secrets.toml 或設置環境變數 FOOTBALL_API_KEY")
    # 為了防止空 Key 發送請求，這裡選擇中止或讓用戶知道
    # sys.exit(1) 

BASE_URL = 'https://v3.football.api-sports.io'
GOOGLE_SHEET_NAME = "數據上傳" 
CSV_FILENAME = "football_data_backup.csv" 

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
    if not API_KEY:
        return None

    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-apisports-key': API_KEY}
    url = f"{BASE_URL}/{endpoint}"
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            # 檢查業務層面的錯誤
            if data.get("errors"):
                print(f"⚠️ API 返回錯誤: {data['errors']}")
                return None
            return data
            
        elif response.status_code == 429:
            print("❌ API 請求過多 (Rate Limit Reached)！暫停 5 秒...")
            time.sleep(5)
            return None
        else:
            print(f"❌ HTTP 錯誤 {response.status_code}: {url}")
            return None
    except Exception as e:
        print(f"❌ 請求異常: {e}")
        return None

# ================= Google Sheet =================
def get_google_spreadsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        # 優先從 st.secrets 讀取 (雲端部署模式)
        if "gcp_service_account" in st.secrets:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        # 本地模式 fallback
        elif os.path.exists("key.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        else:
            print("⚠️ 未找到 Google Credentials (st.secrets 或 key.json)")
            return None
            
        client = gspread.authorize(creds)
        return client.open(GOOGLE_SHEET_NAME)
    except Exception as e:
        print(f"⚠️ Google Sheet 連接失敗: {e}")
        return None

# ================= 數據獲取工具 =================
def get_league_standings(league_id, season):
    data = call_api('standings', {'league': league_id, 'season': season})
    standings_map = {}
    if not data or not data.get('response'): return standings_map
    
    try:
        standings_response = data['response'][0]['league']['standings']
        all_teams = []
        for group in standings_response: all_teams.extend(group)
        for team in all_teams:
            t_id = team['team']['id']
            h_s = team['home']; a_s = team['away']
            standings_map[t_id] = {
                'rank': team['rank'], 'form': team['form'],
                'home_stats': {'played': h_s['played'], 'avg_goals_for': h_s['goals']['for']/(h_s['played'] or 1), 'avg_goals_against': h_s['goals']['against']/(h_s['played'] or 1)},
                'away_stats': {'played': a_s['played'], 'avg_goals_for': a_s['goals']['for']/(a_s['played'] or 1), 'avg_goals_against': a_s['goals']['against']/(a_s['played'] or 1)}
            }
    except Exception as e:
        print(f"⚠️ 解析積分榜失敗: {e}")
        pass
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

def get_injuries_count(fixture_id, home_team_name, away_team_name):
    data = call_api('injuries', {'fixture': fixture_id})
    if not data or not data.get('response'): return 0, 0
    h_c = 0; a_c = 0
    for item in data['response']:
        if item['team']['name'] == home_team_name: h_c += 1
        elif item['team']['name'] == away_team_name: a_c += 1
    return h_c, a_c

def get_best_odds(fixture_id):
    data = call_api('odds', {'fixture': fixture_id})
    if not data or not data.get('response'): return 0, 0, 0
    
    try:
        bks = data['response'][0]['bookmakers']
        # 優先尋找主流公司
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
    except Exception:
        pass # 賠率解析失敗允許靜默，返回 0,0,0
    return 0, 0, 0

def safe_float(val):
    try: return float(val) if val is not None else 0.0
    except: return 0.0

# ================= 數學核心 =================
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

def calculate_advanced_math_probs(h_exp, a_exp):
    prob_exact = {}
    for h in range(10):
        for a in range(10): prob_exact[(h, a)] = poisson_prob(h, h_exp) * poisson_prob(a, a_exp)
    
    h_win = sum(p for (h, a), p in prob_exact.items() if h > a)
    a_win = sum(p for (h, a), p in prob_exact.items() if a > h)
    o25 = sum(p for (h, a), p in prob_exact.items() if h+a > 2.5)
    btts = 1 - sum(p for (h, a), p in prob_exact.items() if h==0 or a==0)
    
    return {'h_win': h_win*100, 'a_win': a_win*100, 'o25': o25*100, 'btts': btts*100}

# ================= 主流程 =================
def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 V38.1 Eco-Mode (省流版) 啟動...")
    if not API_KEY:
        print("⚠️ 警告: 缺少 API Key，程序可能無法正常工作。")

    hk_tz = pytz.timezone('Asia/Hong_Kong')
    utc_now = datetime.now(pytz.utc)
    
    # 優化策略: 3天範圍 (前後各3天)
    from_date = (utc_now - timedelta(days=3)).strftime('%Y-%m-%d')
    to_date = (utc_now + timedelta(days=3)).strftime('%Y-%m-%d')
    season = 2025 # 請每年確認
    
    print(f"📅 掃描範圍: {from_date} 至 {to_date}")
    cleaned_data = []
    value_bets = []

    for lg_id, lg_name in LEAGUE_ID_MAP.items():
        print(f"   🔍 掃描 {lg_name}...")
        standings = get_league_standings(lg_id, season)
        
        # 獲取賽程
        fixtures_data = call_api('fixtures', {'league': lg_id, 'season': season, 'from': from_date, 'to': to_date})
        
        if not fixtures_data or not fixtures_data.get('response'): 
            print("      👉 無賽事")
            continue
            
        fixtures = fixtures_data['response']
        print(f"      👉 找到 {len(fixtures)} 場比賽")
        
        for item in fixtures:
            fix_id = item['fixture']['id']
            # 轉換時間
            t_str = datetime.fromtimestamp(item['fixture']['timestamp'], pytz.utc).astimezone(hk_tz).strftime('%Y-%m-%d %H:%M')
            status = item['fixture']['status']['short']
            
            is_finished = False
            if status in ['FT','AET','PEN']: 
                status_txt = '完場'
                is_finished = True
            elif status in ['1H','2H','HT','LIVE']: status_txt = '進行中'
            elif status in ['PST','CANC','ABD']: status_txt = '延遲/取消'
            else: status_txt = '未開賽'

            h_name = item['teams']['home']['name']; a_name = item['teams']['away']['name']
            h_id = item['teams']['home']['id']; a_id = item['teams']['away']['id']
            sc_h = item['goals']['home']; sc_a = item['goals']['away']

            # 獲取排名
            h_info = standings.get(h_id, {'rank': '?', 'form': '?????'})
            a_info = standings.get(a_id, {'rank': '?', 'form': '?????'})
            
            # 預測數據
            pred_resp = call_api('predictions', {'fixture': fix_id})
            pred_data = pred_resp['response'][0] if pred_resp and pred_resp.get('response') else None
            
            # 計算核心概率
            h_exp, a_exp, src = calculate_split_expected_goals(h_id, a_id, standings, pred_data)
            probs = calculate_advanced_math_probs(h_exp, a_exp)
            
            # API 請求優化: 完場比賽不抓賠率和傷病
            odds_h, odds_d, odds_a = 0,0,0
            inj_h, inj_a = 0,0
            
            if not is_finished:
                odds_h, odds_d, odds_a = get_best_odds(fix_id)
                inj_h, inj_a = get_injuries_count(fix_id, h_name, a_name)
            
            h2h_h, h2h_d, h2h_a = get_h2h_stats(h_id, a_id)

            # Value Bet 判斷
            val_h = ""; val_a = ""
            if odds_h > 0:
                implied_h = 1/odds_h
                if (probs['h_win']/100) > implied_h: val_h = "💰"
            if odds_a > 0:
                implied_a = 1/odds_a
                if (probs['a_win']/100) > implied_a: val_a = "💰"

            if val_h or val_a:
                pick = f"主勝 ({h_name})" if val_h else f"客勝 ({a_name})"
                value_bets.append({'League': lg_name, 'Match': f"{h_name} vs {a_name}", 'Pick': pick, 'Odds': odds_h if val_h else odds_a})

            cleaned_data.append({
                '時間': t_str, '聯賽': lg_name, '主隊': h_name, '客隊': a_name, '狀態': status_txt,
                '主分': sc_h if sc_h is not None else "", '客分': sc_a if sc_a is not None else "",
                '主排名': h_info['rank'], '客排名': a_info['rank'],
                '主走勢': h_info['form'], '客走勢': a_info['form'],
                '主Value': val_h, '客Value': val_a,
                'xG主': round(h_exp,2), 'xG客': round(a_exp,2), '數據源': src,
                '主勝率': round(probs['h_win']), '客勝率': round(probs['a_win']),
                '大2.5': round(probs['o25']), 'BTTS': round(probs['btts']),
                '主賠': odds_h, '客賠': odds_a,
                '主傷': inj_h, '客傷': inj_a, 'H2H主': h2h_h, 'H2H和': h2h_d, 'H2H客': h2h_a
            })
            
            print(f"         ✅ {h_name} vs {a_name} | xG: {h_exp:.2f}-{a_exp:.2f} {val_h}{val_a}")
            time.sleep(0.1) # 短暫休眠防止過快

    if cleaned_data:
        df = pd.DataFrame(cleaned_data)
        
        # 保存 CSV (本地備份)
        try:
            df.to_csv(CSV_FILENAME, index=False, encoding='utf-8-sig')
            print(f"\n💾 數據已備份至: {CSV_FILENAME}")
        except Exception as e:
            print(f"❌ CSV 保存失敗: {e}")

        # 上傳 Google Sheet
        spreadsheet = get_google_spreadsheet()
        if spreadsheet:
            try:
                spreadsheet.sheet1.clear()
                # 確保全是字串以避免格式問題
                spreadsheet.sheet1.update(range_name='A1', values=[df.columns.values.tolist()] + df.astype(str).values.tolist())
                print("✅ Google Sheet 上傳成功")
            except Exception as e: 
                print(f"❌ Google Sheet 上傳失敗: {e}")
        
        if value_bets:
            print("\n💎 精選 VALUE BETS 💎")
            for v in value_bets: print(f"{v['League']} | {v['Match']} | {v['Pick']} @ {v['Odds']}")
    else:
        print("⚠️ 本次運行無數據獲取")

if __name__ == "__main__":
    main()
