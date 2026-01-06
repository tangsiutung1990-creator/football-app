import os
import requests
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# ================= 配置區 =================
API_KEY = '531bb40a089446bdae76a019f2af3beb'
DAYS_TO_FETCH = 2  
GOOGLE_SHEET_FILENAME = "數據上傳" 
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_KEY_FILE = os.path.join(BASE_DIR, 'key.json')

# ================= 翻譯字典 (保留你的設定) =================
LEAGUE_MAP = {
    "PL": "英超", "ELC": "英冠", "PD": "西甲", "SA": "意甲", "BL1": "德甲",
    "FL1": "法甲", "DED": "荷甲", "PPL": "葡超", "CL": "歐聯", "BSA": "巴甲",
    "CLI": "自由盃", "WC": "世界盃", "EC": "歐國盃", "FAC": "足總盃", "CDR": "國王盃",
    "UEL": "歐霸", "UECL": "歐協聯"
}
NAME_MAP = {
    "Arsenal FC": "阿仙奴", "Aston Villa FC": "阿士東維拉", "Liverpool FC": "利物浦", 
    "Manchester City FC": "曼城", "Manchester United FC": "曼聯", "Chelsea FC": "車路士",
    "Real Madrid CF": "皇馬", "FC Barcelona": "巴塞隆拿", "Juventus FC": "祖雲達斯",
    # ... (程式會優先用呢度既名) ...
}

def get_google_sheet_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
    client = gspread.authorize(creds)
    return client

def fetch_data(url):
    headers = {'X-Auth-Token': API_KEY}
    for attempt in range(3):
        try:
            res = requests.get(url, headers=headers, timeout=30)
            if res.status_code == 200: return res.json()
            elif res.status_code == 429:
                print(f"⚠️ API 請求過快 (429)，休息 10 秒...")
                time.sleep(10)
            else:
                print(f"⚠️ 獲取失敗 (Status: {res.status_code}) - URL: {url}")
                time.sleep(2)
        except Exception as e: 
            print(f"⚠️ 連線錯誤: {e}")
            time.sleep(2)
    return None

def main():
    today = datetime.now()
    start_date = today - timedelta(days=1)
    end_date = today + timedelta(days=DAYS_TO_FETCH)
    date_from, date_to = start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

    print(f"1. 正在搜尋賽程 ({date_from} ~ {date_to})...")
    data = fetch_data(f"https://api.football-data.org/v4/matches?dateFrom={date_from}&dateTo={date_to}")
    matches = data.get('matches', []) if data else []
    
    if not matches:
        print("⚠️ 暫無賽事。")
        return

    # --- 下載積分榜 ---
    leagues = list(set([m['competition']['code'] for m in matches]))
    print(f"2. 下載積分榜數據 (聯賽數: {len(leagues)})...")
    stats_db = {}
    for code in leagues:
        d = fetch_data(f"https://api.football-data.org/v4/competitions/{code}/standings")
        if d:
            for t in d.get('standings', []):
                table_type = t['type']
                if table_type in ['TOTAL', 'HOME', 'AWAY']:
                    for r in t.get('table', []):
                        name = r['team']['name']
                        gf, ga, pg = r.get('goalsFor', 0), r.get('goalsAgainst', 0), r.get('playedGames', 1)
                        if pg == 0: pg = 1
                        if name not in stats_db: stats_db[name] = {}
                        stats_db[name][table_type] = {'rank': str(r.get('position', '')), 'gf': gf, 'ga': ga, 'pg': pg}
        time.sleep(2)

    # --- 分析 ---
    print(f"3. 正在逐場分析 (含 H2H, 勝負, 大細)...")
    
    # 🔥 修改標題：加入 "主預測" 和 "客預測"
    all_rows = [["時間", "狀態", "聯賽", "主隊", "客隊", 
                 "主攻(H)", "主防(H)", "客攻(A)", "客防(A)", 
                 "H2H", "主預測", "客預測", "總球數", "主分", "客分"]]

    count = 0
    for m in matches:
        count += 1
        try:
            h, a = m['homeTeam']['name'], m['awayTeam']['name']
            mid, league_code, status_raw = m['id'], m['competition']['code'], m['status']
            
            print(f"   [{count}/{len(matches)}] {NAME_MAP.get(h, h)} vs {NAME_MAP.get(a, a)}")

            # H2H
            h2h_str = "N/A"
            try:
                h2h_data = fetch_data(f"https://api.football-data.org/v4/matches/{mid}/head2head")
                if h2h_data:
                    agg = h2h_data.get('aggregates', {})
                    h2h_str = f"{agg.get('homeTeamWins', 0)}-{agg.get('draws', 0)}-{agg.get('awayTeamWins', 0)}"
            except: pass
            time.sleep(6.5) # 避 429

            # 時間與狀態
            dt = datetime.strptime(m['utcDate'], "%Y-%m-%dT%H:%M:%SZ")
            t_str = (dt + timedelta(hours=8)).strftime("%m/%d %H:%M")
            
            status_display = "未開賽"
            s_h, s_a = m['score']['fullTime']['home'], m['score']['fullTime']['away']
            score_h_str, score_a_str = "-", "-"

            if status_raw == 'FINISHED':
                status_display = "完場"
                score_h_str, score_a_str = str(s_h), str(s_a)
            elif status_raw == 'IN_PLAY':
                status_display = "🔴進行中"
                score_h_str = str(s_h) if s_h is not None else "0"
                score_a_str = str(s_a) if s_a is not None else "0"

            # 🔥 核心預測算法 🔥
            h_data = stats_db.get(h, {})
            a_data = stats_db.get(a, {})
            h_stat = h_data.get('HOME', h_data.get('TOTAL', {'gf':0, 'ga':0, 'pg':1}))
            a_stat = a_data.get('AWAY', a_data.get('TOTAL', {'gf':0, 'ga':0, 'pg':1}))

            def avg(val, games): return val/games if games > 0 else 0
            
            # 主隊理論入球 = (主隊主場攻力 + 客隊客場失球) / 2
            exp_h = (avg(h_stat['gf'], h_stat['pg']) + avg(a_stat['ga'], a_stat['pg'])) / 2
            
            # 客隊理論入球 = (客隊客場攻力 + 主隊主場失球) / 2
            exp_a = (avg(a_stat['gf'], a_stat['pg']) + avg(h_stat['ga'], h_stat['pg'])) / 2
            
            total_goals = exp_h + exp_a

            row = [
                t_str, status_display, LEAGUE_MAP.get(league_code, league_code), 
                NAME_MAP.get(h, h), NAME_MAP.get(a, a),
                round(avg(h_stat['gf'], h_stat['pg']), 2), round(avg(h_stat['ga'], h_stat['pg']), 2), 
                round(avg(a_stat['gf'], a_stat['pg']), 2), round(avg(a_stat['ga'], a_stat['pg']), 2), 
                h2h_str, 
                round(exp_h, 2), # 主預測
                round(exp_a, 2), # 客預測
                round(total_goals, 2), # 總球數
                score_h_str, score_a_str
            ]
            all_rows.append(row)

        except Exception as e:
            print(f"   跳過: {e}")
            pass

    # --- 上傳 ---
    try:
        client = get_google_sheet_client()
        sheet = client.open(GOOGLE_SHEET_FILENAME).sheet1
        sheet.clear() 
        sheet.update(all_rows) 
        print(f"✅ 成功更新 {len(all_rows)-1} 場賽事。")
    except Exception as e:
        print(f"❌ 上傳失敗: {e}")

if __name__ == "__main__":
    main()
