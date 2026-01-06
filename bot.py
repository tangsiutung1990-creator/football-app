# 檔案名稱: bot.py (前身是 football.py)
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

# ================= 2. 球隊翻譯 =================
NAME_MAP = {
    "Arsenal FC": "阿仙奴", "Aston Villa FC": "阿士東維拉", "AFC Bournemouth": "般尼茅夫",
    "Brentford FC": "賓福特", "Brighton & Hove Albion FC": "白禮頓",
    "Chelsea FC": "車路士", "Crystal Palace FC": "水晶宮", "Everton FC": "愛華頓",
    "Fulham FC": "富咸", "Ipswich Town FC": "葉士域治", "Leicester City FC": "李斯特城",
    "Liverpool FC": "利物浦", "Manchester City FC": "曼城", "Manchester United FC": "曼聯",
    "Newcastle United FC": "紐卡素", "Nottingham Forest FC": "諾定咸森林",
    "Southampton FC": "修咸頓", "Tottenham Hotspur FC": "熱刺",
    "West Ham United FC": "韋斯咸", "Wolverhampton Wanderers FC": "狼隊",
    "Leeds United FC": "列斯聯", "Sunderland AFC": "新特蘭", "Middlesbrough FC": "米杜士堡",
    "Blackburn Rovers FC": "布力般流浪", "Norwich City FC": "諾域治", "Stoke City FC": "史篤城",
    "Derby County FC": "打吡郡", "Hull City AFC": "侯城", "Watford FC": "屈福特",
    "Millwall FC": "米禾爾", "Swansea City AFC": "史雲斯", "Bristol City FC": "布里斯托城",
    "Preston North End FC": "普雷斯頓", "Portsmouth FC": "樸茨茅夫",
    "Birmingham City FC": "伯明翰", "Coventry City FC": "高雲地利", "Burnley FC": "般尼",
    "Sheffield United FC": "錫菲聯", "Oxford United FC": "牛津聯", "Luton Town FC": "盧頓",
    "Queens Park Rangers FC": "QPR", "Sheffield Wednesday FC": "錫周三", "West Bromwich Albion FC": "西博",
    "Real Madrid CF": "皇馬", "FC Barcelona": "巴塞隆拿", "Atlético de Madrid": "馬體會",
    "Girona FC": "基羅納", "Real Sociedad": "皇家蘇斯達", "Athletic Club": "畢爾包",
    "Real Betis Balompié": "貝迪斯", "Villarreal CF": "維拉利爾", "Sevilla FC": "西維爾",
    "Valencia CF": "華倫西亞", "RCD Mallorca": "馬略卡", "CA Osasuna": "奧沙辛拿",
    "Celta de Vigo": "切爾達", "Rayo Vallecano": "華歷簡奴", "Getafe CF": "加泰",
    "RCD Espanyol de Barcelona": "愛斯賓奴", "Real Valladolid CF": "華拉度列",
    "UD Las Palmas": "拉斯彭馬斯", "CD Leganés": "雷加利斯", "Deportivo Alavés": "艾拉維斯",
    "FC Internazionale Milano": "國米", "AC Milan": "AC米蘭", "Juventus FC": "祖雲達斯",
    "SSC Napoli": "拿玻里", "AS Roma": "羅馬", "Atalanta BC": "亞特蘭大", "SS Lazio": "拉素",
    "ACF Fiorentina": "費倫天拿", "Bologna FC 1909": "博洛尼亞", "Torino FC": "拖連奴",
    "Udinese Calcio": "烏甸尼斯", "Genoa CFC": "熱拿亞", "Parma Calcio 1913": "帕爾馬",
    "Hellas Verona FC": "維罗納", "Empoli FC": "安玻里", "US Lecce": "萊切",
    "AC Monza": "蒙沙", "Cagliari Calcio": "卡利亞里", "Venezia FC": "威尼斯", "Como 1907": "科木",
    "FC Bayern München": "拜仁", "Bayer 04 Leverkusen": "利華古遜", "Borussia Dortmund": "多蒙特",
    "RB Leipzig": "萊比錫", "VfB Stuttgart": "史特加", "Eintracht Frankfurt": "法兰克福",
    "TSG 1899 Hoffenheim": "賀芬咸", "SV Werder Bremen": "雲達不萊梅", "VfL Wolfsburg": "禾夫斯堡",
    "SC Freiburg": "弗賴堡", "1. FC Union Berlin": "柏林聯", "1. FSV Mainz 05": "緬恩斯",
    "Borussia Mönchengladbach": "慕遜加柏", "FC Augsburg": "奧格斯堡", "1. FC Heidenheim 1846": "海登咸",
    "FC St. Pauli": "聖保利", "Holstein Kiel": "基爾", "VfL Bochum 1848": "波琴",
    "Paris Saint-Germain FC": "PSG", "AS Monaco FC": "摩納哥", "Olympique de Marseille": "馬賽",
    "Olympique Lyonnais": "里昂", "LOSC Lille": "里爾", "OGC Nice": "尼斯", "RC Lens": "朗斯",
    "Stade Rennais FC 1901": "雷恩", "Stade de Reims": "兰斯", "Toulouse FC": "圖卢兹",
    "AFC Ajax": "阿積士", "PSV Eindhoven": "PSV燕豪芬", "Feyenoord Rotterdam": "飛燕諾",
    "AZ Alkmaar": "阿爾克馬爾", "FC Twente '65": "泰温特", "FC Utrecht": "烏德勒支",
    "SL Benfica": "賓菲加", "FC Porto": "波圖", "Sporting Clube de Portugal": "士砵亭",
    "SC Braga": "布拉加", "Vitória SC": "甘馬雷斯", "Boavista FC": "博維斯塔",
    "Celtic FC": "些路迪", "Rangers FC": "格拉斯哥流浪", "Galatasaray SK": "加拉塔沙雷",
    "Fenerbahçe SK": "費倫巴治", "FC Shakhtar Donetsk": "薩克達", "FC Salzburg": "萨尔斯堡",
    "Club Brugge KV": "布魯日", "BSC Young Boys": "年青人", "GNK Dinamo Zagreb": "薩格勒布戴拿模",
    "Sporting CP": "士砵亭"
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
            time.sleep(3) 
        except: time.sleep(3)
    return None

def main():
    # --- 計算日期 (昨+今+未來) ---
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

    # --- 獲取積分榜 (含入球數據) ---
    leagues = list(set([m['competition']['code'] for m in matches]))
    print(f"2. 發現 {len(matches)} 場賽事，涉及聯賽: {leagues}")
    print("   正在下載數據 (包含攻防能力值)...")
    
    stats_db = {}
    for code in leagues:
        print(f"   -> 正在下載 {code} 積分榜...")
        d = fetch_data(f"https://api.football-data.org/v4/competitions/{code}/standings")
        if d:
            for t in d.get('standings', []):
                if t['type'] == 'TOTAL':
                    for r in t.get('table', []):
                        name = r['team']['name']
                        gf = r.get('goalsFor', 0)    
                        ga = r.get('goalsAgainst', 0) 
                        pg = r.get('playedGames', 1)  
                        if pg == 0: pg = 1
                        
                        stats_db[name] = {
                            'rank': str(r.get('position', '')),
                            'form': str(r.get('form', '')).replace(",", "") if r.get('form') else "",
                            'gf': gf, 'ga': ga, 'pg': pg
                        }
        time.sleep(2)

    # --- 整理數據 ---
    print("3. 正在整理數據 (含即時比分)...")
    
    # 標題列 (注意：尾部增加了比分欄位)
    all_rows = [["時間", "聯賽", "主隊", "客隊", "主排", "客排", "主近", "客近", 
                 "主勝", "和", "客勝", "主攻", "主防", "客攻", "客防", "主分", "客分", "備註"]]

    for m in matches:
        try:
            h = m['homeTeam']['name']
            a = m['awayTeam']['name']
            league_code = m['competition']['code']

            # 時間處理 (修正時差)
            dt = datetime.strptime(m['utcDate'], "%Y-%m-%dT%H:%M:%SZ")
            hk_time = dt + timedelta(hours=8)
            t_str = hk_time.strftime("%m/%d %H:%M") 
            
            # 獲取統計
            h_stat = stats_db.get(h, {'rank': '', 'form': '', 'gf':0, 'ga':0, 'pg':1})
            a_stat = stats_db.get(a, {'rank': '', 'form': '', 'gf':0, 'ga':0, 'pg':1})
            
            # 平均入球
            def calc_avg(val, games): return round(val/games, 2) if games > 0 else 0
            h_avg_gf = calc_avg(h_stat['gf'], h_stat['pg']) 
            h_avg_ga = calc_avg(h_stat['ga'], h_stat['pg']) 
            a_avg_gf = calc_avg(a_stat['gf'], a_stat['pg']) 
            a_avg_ga = calc_avg(a_stat['ga'], a_stat['pg'])

            # 🔥🔥🔥 抓取比分 (新增功能) 🔥🔥🔥
            # 如果比賽未開始，s_h 同 s_a 會係 None
            s_h = m['score']['fullTime']['home']
            s_a = m['score']['fullTime']['away']
            
            # 將 None 轉為空字串，否則轉為文字
            score_h_str = str(s_h) if s_h is not None else ""
            score_a_str = str(s_a) if s_a is not None else ""

            row = [
                t_str, LEAGUE_MAP.get(league_code, league_code), 
                NAME_MAP.get(h, h), NAME_MAP.get(a, a),
                h_stat['rank'], a_stat['rank'],
                h_stat['form'], a_stat['form'],
                "","","", # 賠率 (空)
                h_avg_gf, h_avg_ga, 
                a_avg_gf, a_avg_ga, 
                score_h_str, score_a_str, # 🔥 這裡填入比分
                "" 
            ]
            all_rows.append(row)
        except: pass

    # --- 上傳 ---
    print(f"4. 正在連線到 Google Sheet ({GOOGLE_SHEET_FILENAME})...")
    try:
        client = get_google_sheet_client()
        sh = client.open(GOOGLE_SHEET_FILENAME)
        sheet = sh.sheet1
        sheet.clear() 
        sheet.update(all_rows) 
        print(f"✅ 成功！已更新 {len(all_rows)-1} 場賽事 (含比分) 到雲端。")
        
    except FileNotFoundError:
        print(f"❌ 錯誤：找不到 key.json")
    except Exception as e:
        print(f"❌ 上傳失敗: {e}")

   # input("按 Enter 離開...")

if __name__ == "__main__":

    main()
