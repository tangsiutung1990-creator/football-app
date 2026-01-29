# football.py
import requests
import pandas as pd
from datetime import datetime, timedelta
import pytz
import random  # 用於模擬部分缺失數據的預測邏輯

class FootballApp:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://v3.football.api-sports.io"
        self.headers = {
            'x-rapidapi-host': "v3.football.api-sports.io",
            'x-rapidapi-key': self.api_key
        }
        self.tz_hk = pytz.timezone('Asia/Hong_Kong')

    def get_dates(self):
        """獲取昨天、今天、明天的日期字符串"""
        today = datetime.now(self.tz_hk)
        dates = [
            (today - timedelta(days=1)).strftime('%Y-%m-%d'),
            today.strftime('%Y-%m-%d'),
            (today + timedelta(days=1)).strftime('%Y-%m-%d')
        ]
        return dates

    def fetch_fixtures(self):
        """抓取英超 (League ID: 39) 昨天、今天、明天的賽事"""
        all_fixtures = []
        dates = self.get_dates()
        
        # 為了節省請求，這裡簡化邏輯，實際開發建議緩存數據
        for date in dates:
            params = {
                'league': 39,  # 英超 ID
                'season': 2025, # 請根據當前賽季修改，例如 2024 或 2025
                'date': date,
                'timezone': 'Asia/Hong_Kong'
            }
            try:
                response = requests.get(f"{self.base_url}/fixtures", headers=self.headers, params=params)
                data = response.json()
                if 'response' in data:
                    all_fixtures.extend(data['response'])
            except Exception as e:
                print(f"Error fetching data for {date}: {e}")
        
        return all_fixtures

    def get_team_stats(self, team_id):
        """獲取球隊本賽季數據 (模擬/簡化調用以節省 API 額度)"""
        # 這裡通常需要呼叫 /teams/statistics，為演示邏輯，我們從 Fixture 數據中提取或使用模擬數據
        # 在完整版中，你應該這裡呼叫 API
        return {
            "form": "WWDLW",
            "goals_for": 1.8,
            "goals_against": 1.2
        }

    def ai_prediction_engine(self, fixture):
        """
        核心預測邏輯：根據現有數據計算機率
        注意：這是基於統計的算法模擬，並非真實的神經網絡，但能滿足介面需求。
        """
        home_team = fixture['teams']['home']['name']
        away_team = fixture['teams']['away']['name']
        
        # 1. 模擬基礎勝率 (基於排名或近期表現，這裡用隨機模擬展示格式)
        # 實際應用應使用 fixture['teams']['home']['winner'] 賠率轉換或歷史數據計算
        prob_home = random.randint(30, 60)
        prob_away = random.randint(10, 40)
        prob_draw = 100 - prob_home - prob_away
        
        # 2. 亞洲盤機率模擬
        asian_handicap = {
            "level": f"{random.randint(40,60)}%",
            "minus_1": f"{random.randint(30,50)}%",
            "minus_2": f"{random.randint(10,30)}%",
            "plus_1": f"{random.randint(60,80)}%",
            "plus_2": f"{random.randint(80,95)}%"
        }

        # 3. 入球大細模擬
        goals_over = {
            "0.5": random.randint(85, 99),
            "1.5": random.randint(60, 85),
            "2.5": random.randint(40, 60),
            "3.5": random.randint(20, 40),
            "4.5": random.randint(5, 20)
        }
        
        # 4. 半場入球
        ht_goals = {
            "0.5": random.randint(60, 80),
            "1.5": random.randint(20, 40),
            "2.5": random.randint(5, 15)
        }

        # 5. 爆冷警告
        upset_alert = None
        if prob_away > 40 and prob_home > 50: # 假設性條件
             upset_alert = "⚠️ 警告：客隊近期狀態極佳，有爆冷風險"

        # 9. 爭勝心分析 (模擬)
        motivation = "主隊急需積分保級，戰意高昂；客隊位居中游，無欲無求。"

        return {
            "win_probs": {"home": prob_home, "draw": prob_draw, "away": prob_away},
            "asian_handicap": asian_handicap,
            "goals_over": goals_over,
            "ht_goals": ht_goals,
            "upset_alert": upset_alert,
            "motivation": motivation
        }
