import os
import requests
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# ================= 配置區 =================
API_KEY = '531bb40a089446bdae76a019f2af3beb'

# 抓取範圍：(1=捉埋尋日, 2=捉埋尋日+今日+聽日)
DAYS_TO_FETCH = 2  

GOOGLE_SHEET_FILENAME = "數據上傳" 

# 自動修正路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_KEY_FILE = os.path.join(BASE_DIR, 'key.json')

# ================= 1. 聯賽翻譯 =================
LEAGUE_MAP = {
    "PL": "英超", "ELC": "英冠", "PD": "西甲", "SA": "意甲", "BL1": "德甲",
    "FL1": "法甲", "DED": "荷甲", "PPL": "葡超", "CL": "歐聯", "BSA": "巴甲",
    "CLI": "自由盃", "WC": "世界盃", "EC": "歐國盃", "FAC": "足總盃", "CDR": "國王盃",
    "UEL": "歐霸", "UECL": "歐協聯"
}

# ================= 2. 球隊翻譯 (省略部分以節省篇幅, 照舊) =================
NAME_MAP = {
    "Arsenal FC": "阿仙奴", "Aston Villa FC": "阿士東維拉", "Liverpool FC": "利物浦", 
    "Manchester City FC": "曼城", "Manchester United FC": "曼聯", "Chelsea FC": "車路士",
    "Real Madrid CF": "皇馬", "FC Barcelona": "巴塞隆拿", "Juventus FC": "祖雲達斯",
    # ... (程式會優先用呢度既名，無就會用英文原名) ...
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
            # 成功
            if res.status_code == 200: 
                return res.json()
            # 請求太快
            elif res.status_code == 429:
                print(f"⚠️ API 請求過快 (429)，休息 10 秒...")
                time.sleep(10)
            # 其他錯誤 (例如 403 權限不足, 404 找不到)
            else:
                print(f"⚠️ 獲取失敗 (Status: {res.status_code}) - URL: {url}")
                time.sleep(2)
        except Exception as e: 
            print(f"⚠️ 連線錯誤: {e}")
            time.sleep(2)
    return None

def main():
    # --- 計算日期 ---
    today = datetime.now()
    start_date = today - timedelta(days=1)
    end_date = today + timedelta(days=DAYS_TO_FETCH)
    date_from, date_to = start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

    print(f"1. 正在搜尋賽程 (由 {date_from} 到 {date_to})...")
    
    url = f"https://api.football-data.org/v4/matches?dateFrom={date_from}&dateTo={date_to}"
    data = fetch_data(url)
    matches = data.get('matches', []) if data else []
    
    if not matches:
        print("⚠️ 這段時間暫無重點賽事。")
        return

    # --- 獲取積分榜 (主/客/總) ---
    leagues = list(set([m['competition']['code'] for m in matches]))
    print(f"2. 發現 {len(matches)} 場賽事，涉及聯賽: {leagues}")
    print("   正在下載積分榜數據...")
    
    stats_db = {}
    for code in leagues:
        # print(f"   -> 下載 {code}...")
        d = fetch_data(f"https://api.football-data.org/v4/competitions/{code}/standings")
        if d:
            for t in d.get('standings', []):
                table_type = t['type']
                if table_type in ['TOTAL', 'HOME', 'AWAY']:
                    for r in t.get('table', []):
                        name = r['team']['name']
                        gf = r.get('goalsFor', 0)    
                        ga = r.get('goalsAgainst', 0) 
                        pg = r.get('playedGames', 1)  
                        if pg == 0: pg = 1
                        
                        if name not in stats_db: stats_db[name] = {}
                        stats_db[name][table_type] = {
                            'rank': str(r.get('position', '')),
                            'gf': gf, 'ga': ga, 'pg': pg
                        }
        time.sleep(2)

    # --- 整理數據 + 抓取 H2H ---
    print(f"3. 正在逐場分析 (含 H2H 對賽往績)...")
    
    # 新增 H2H 欄位
    all_rows = [["時間", "狀態", "聯賽", "主隊", "客隊", 
                 "主攻(H)", "主防(H)", "客攻(A)", "客防(A)", 
                 "H2H (主-和-客)", "預測入球", "主分", "客分"]]

    count = 0
    total_matches = len(matches)

    for m in matches:
        count += 1
        try:
            h = m['homeTeam']['name']
            a = m['awayTeam']['name']
            mid = m['id'] 
            league_code = m['competition']['code']
            status_raw = m['status']

            print(f"   [{count}/{total_matches}] 分析: {NAME_MAP.get(h, h)} vs {NAME_MAP.get(a, a)}...")

            # --- 🔥 H2H 抓取 🔥 ---
            h2h_str = "N/A"
            try:
                # 這裡會用到上面的 fetch_data，如果失敗會印出原因
                h2h_data = fetch_data(f"https://api.football-data.org/v4/matches/{mid}/head2head")
                if h2h_data:
                    agg = h2h_data.get('aggregates', {})
                    h2h_str = f"{agg.get('homeTeamWins', 0)}-{agg.get('draws', 0)}-{agg.get('awayTeamWins', 0)}"
            except:
                pass
            
            # 強制休息，避免 429
            time.sleep(6.5)

            # --- 處理其他數據 ---
            dt = datetime.strptime(m['utcDate'], "%Y-%m-%dT%H:%M:%SZ")
            hk_time = dt + timedelta(hours=8)
            t_str = hk_time.strftime("%m/%d %H:%M") 

            # 狀態
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
            elif status_raw == 'PAUSED': status_display = "中場"
            elif status_raw == 'POSTPONED': status_display = "延期"

            # 攻防數據
            h_data = stats_db.get(h, {})
            a_data = stats_db.get(a, {})
            h_stat = h_data.get('HOME', h_data.get('TOTAL', {'gf':0, 'ga':0, 'pg':1}))
            a_stat = a_data.get('AWAY', a_data.get('TOTAL', {'gf':0, 'ga':0, 'pg':1}))

            def calc_avg(val, games): return round(val/games, 2) if games > 0 else 0
            h_home_gf = calc_avg(h_stat['gf'], h_stat['pg']) 
            h_home_ga = calc_avg(h_stat['ga'], h_stat['pg']) 
            a_away_gf = calc_avg(a_stat['gf'], a_stat['pg']) 
            a_away_ga = calc_avg(a_stat['ga'], a_stat['pg'])

            # 預測
            expected_goals = (h_home_gf + a_away_ga) / 2 + (a_away_gf + h_home_ga) / 2
            expected_goals_str = f"{expected_goals:.2f}"

            row = [
                t_str, status_display, LEAGUE_MAP.get(league_code, league_code), 
                NAME_MAP.get(h, h), NAME_MAP.get(a, a),
                h_home_gf, h_home_ga, 
                a_away_gf, a_away_ga, 
                h2h_str, 
                expected_goals_str, 
                score_h_str, score_a_str
            ]
            all_rows.append(row)

        except Exception as e:
            print(f"   跳過: {e}")
            pass

    # --- 上傳 ---
    print(f"4. 正在上傳到 Google Sheet...")
    try:
        client = get_google_sheet_client()
        sh = client.open(GOOGLE_SHEET_FILENAME)
        sheet = sh.sheet1
        sheet.clear() 
        sheet.update(all_rows) 
        print(f"✅ 成功！已更新 {len(all_rows)-1} 場賽事。")
    except Exception as e:
        print(f"❌ 上傳失敗: {e}")

if __name__ == "__main__":
    main()
