import datetime
import requests
import json
import random

# ================= 配置區 =================
# 請在這裡填入你的 API 資訊
YOUR_API_URL = "https://api.example.com/matches/today"  # 替換成你的真實 API 網址
# 如果你的 API 需要 Header (例如 Key)，請在下方設定
YOUR_API_HEADERS = None 
# 例如: YOUR_API_HEADERS = {"x-api-key": "123456"}
# =========================================

def get_iso_time(hours_offset=0):
    now = datetime.datetime.now()
    future = now + datetime.timedelta(hours=hours_offset)
    return future.isoformat()

def get_todays_matches():
    """
    負責抓取賽事數據。
    如果 YOUR_API_URL 是預設值，會回傳模擬數據 (Mock Data)。
    """
    matches = []
    
    # 判斷是否使用真實 API
    use_real_api = "example.com" not in YOUR_API_URL

    if use_real_api:
        try:
            print(f"正在連線至 API: {YOUR_API_URL}")
            response = requests.get(YOUR_API_URL, headers=YOUR_API_HEADERS, timeout=15)
            
            if response.status_code == 200:
                real_data = response.json()
                # 假設 real_data 是一個列表
                if isinstance(real_data, list):
                    for item in real_data:
                        matches.append(transform_data(item))
                else:
                    # 如果 API 回傳格式不同 (例如包在 'data' 欄位內)，請在這裡調整
                    print("API 回傳格式可能不符，請檢查 football.py")
                    
                return matches
            else:
                print(f"API 請求失敗，代碼: {response.status_code}")
                return get_mock_data()
                
        except Exception as e:
            print(f"獲取數據錯誤: {e}")
            return get_mock_data()
    else:
        print("目前使用模擬數據 (Mock Data)")
        return get_mock_data()

def transform_data(item):
    """
    將你的 API 數據格式轉換為 App 統一格式。
    請根據你的真實 API 回傳欄位修改右邊的 `item.get(...)`
    """
    return {
        "id": str(item.get("match_id", random.randint(1000,9999))),
        "league": item.get("league_name", "Unknown League"),
        "homeTeam": { 
            "id": "h_" + str(item.get("home_id", "0")), 
            "name": item.get("home_team", "Home"), 
            "logo": item.get("home_logo", "https://picsum.photos/40/40?random=1"),
            "leaguePosition": item.get("home_rank", 0)
        },
        "awayTeam": { 
            "id": "a_" + str(item.get("away_id", "0")), 
            "name": item.get("away_team", "Away"), 
            "logo": item.get("away_logo", "https://picsum.photos/40/40?random=2"),
            "leaguePosition": item.get("away_rank", 0)
        },
        "startTime": item.get("time", get_iso_time(0)), 
        "status": "NOT_STARTED", # 預設未開賽，你也可以根據 API 時間判斷
        "baseStats": {
            # 6. 主客和勝率
            "homeWinRate": item.get("stats", {}).get("home_win_rate", 50), 
            "awayWinRate": item.get("stats", {}).get("away_win_rate", 50),
            
            # 7 & 8. 入球大細機率
            "homeOver05Rate": item.get("stats", {}).get("home_over_05", 90),
            "homeOver15Rate": item.get("stats", {}).get("home_over_15", 70),
            "homeOver25Rate": item.get("stats", {}).get("home_over_25", 50),
            "homeOver35Rate": item.get("stats", {}).get("home_over_35", 30),
            
            "awayOver05Rate": item.get("stats", {}).get("away_over_05", 85),
            "awayOver15Rate": item.get("stats", {}).get("away_over_15", 65),
            "awayOver25Rate": item.get("stats", {}).get("away_over_25", 45),
            "awayOver35Rate": item.get("stats", {}).get("away_over_35", 25),
            
            # 近況 (W=Win, D=Draw, L=Loss)
            "recentFormHome": item.get("stats", {}).get("form_home", ["D", "D", "W", "L", "D"]),
            "recentFormAway": item.get("stats", {}).get("form_away", ["W", "L", "W", "D", "L"])
        }
    }

def get_mock_data():
    """ 模擬數據，當沒有真實 API 時顯示 """
    return [
        {
            "id": "m1",
            "league": "英格蘭超級聯賽",
            "homeTeam": { "id": "t1", "name": "曼城", "logo": "https://picsum.photos/40/40?random=1", "leaguePosition": 2 },
            "awayTeam": { "id": "t2", "name": "阿仙奴", "logo": "https://picsum.photos/40/40?random=2", "leaguePosition": 1 },
            "startTime": get_iso_time(2),
            "status": "NOT_STARTED",
            "baseStats": {
                "homeWinRate": 85, "awayWinRate": 70,
                "homeOver05Rate": 98, "homeOver15Rate": 88, "homeOver25Rate": 65, "homeOver35Rate": 45,
                "awayOver05Rate": 92, "awayOver15Rate": 80, "awayOver25Rate": 55, "awayOver35Rate": 35,
                "recentFormHome": ['W', 'W', 'D', 'W', 'W'],
                "recentFormAway": ['W', 'W', 'W', 'L', 'W']
            }
        },
        {
            "id": "m2",
            "league": "西班牙甲組聯賽",
            "homeTeam": { "id": "t3", "name": "皇家馬德里", "logo": "https://picsum.photos/40/40?random=3", "leaguePosition": 1 },
            "awayTeam": { "id": "t4", "name": "巴塞隆拿", "logo": "https://picsum.photos/40/40?random=4", "leaguePosition": 2 },
            "startTime": get_iso_time(5),
            "status": "NOT_STARTED",
            "baseStats": {
                "homeWinRate": 82, "awayWinRate": 78,
                "homeOver05Rate": 95, "homeOver15Rate": 90, "homeOver25Rate": 75, "homeOver35Rate": 55,
                "awayOver05Rate": 94, "awayOver15Rate": 89, "awayOver25Rate": 76, "awayOver35Rate": 60,
                "recentFormHome": ['W', 'D', 'W', 'W', 'D'],
                "recentFormAway": ['W', 'W', 'W', 'W', 'W']
            }
        }
    ]
